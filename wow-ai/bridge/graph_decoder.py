"""Single-token CUDA graph for the local, batch-one GPT2 speech decoder.

Prefix evaluation remains unmodified. Fixed KV buffers remove growing Python
and allocation work; each step masks unused slots and uses the true position.
"""
import types


class GraphDecoder:
    def __init__(self, t3, capacity=768, batch=8):
        import torch
        from transformers.generation.logits_process import LogitsProcessorList, TemperatureLogitsWarper, TopKLogitsWarper, TopPLogitsWarper
        self.torch = torch
        self.t3 = t3
        self.capacity = capacity
        self.batch = batch
        device = next(t3.parameters()).device
        dtype = next(t3.parameters()).dtype
        self.position = torch.zeros(1, dtype=torch.long, device=device)
        self.token = torch.zeros((1, 1), dtype=torch.long, device=device)
        self.count = torch.zeros(1, dtype=torch.long, device=device)
        self.tokens = torch.zeros((1, 1008), dtype=torch.long, device=device)
        self.seen = torch.zeros((1, t3.speech_head.out_features), dtype=torch.bool, device=device)
        self.indices = torch.arange(capacity, device=device)
        self.past = tuple((torch.zeros((1, block.attn.num_heads, capacity, block.attn.head_dim), device=device, dtype=dtype),
                           torch.zeros((1, block.attn.num_heads, capacity, block.attn.head_dim), device=device, dtype=dtype))
                          for block in t3.tfmr.h)
        self.processors = LogitsProcessorList([TemperatureLogitsWarper(0.7), TopKLogitsWarper(1000), TopPLogitsWarper(0.95)])
        self.graph = None
        self.logits = None

    def reset(self, past, token):
        length = past[0][0].shape[-2]
        if length + self.batch >= self.capacity:
            raise ValueError('Speech prefix exceeds the fixed decoder capacity')
        for destination, source in zip(self.past, past):
            for dst, src in zip(destination, source):
                dst.zero_()
                dst[:, :, :length].copy_(src)
        self.position.fill_(length)
        self.token.copy_(token)
        self.count.fill_(1)
        self.tokens.zero_()
        self.tokens[:, :1].copy_(token)
        self.seen.zero_()
        self.seen.scatter_(1, token, True)

    def step(self):
        torch = self.torch
        mask = torch.where(self.indices <= self.position, 0.0, torch.finfo(self.past[0][0].dtype).min).to(self.past[0][0].dtype)
        self.mask = mask.view(1, 1, 1, -1)
        output = self.t3.tfmr(inputs_embeds=self.t3.speech_emb(self.token), past_key_values=self.past,
                              position_ids=self.position.view(1, 1), use_cache=True)
        self.logits = self.t3.speech_head(output[0])[:, -1, :]
        logits = self.processors(self.token, self.logits)
        penalized = torch.where(logits < 0, logits * 1.2, logits / 1.2)
        logits = torch.where(self.seen, penalized, logits)
        next_token = torch.multinomial(torch.softmax(logits, dim=-1), num_samples=1)
        self.tokens.index_copy_(1, self.count, next_token)
        self.token.copy_(next_token)
        self.seen.scatter_(1, next_token, True)
        self.position.add_(1)
        self.count.add_(1)

    def capture(self, past, token):
        torch = self.torch
        original_forwards = []
        graph_decoder = self

        def static_attention(attn, hidden_states, layer_past=None, attention_mask=None, head_mask=None,
                             encoder_hidden_states=None, encoder_attention_mask=None, use_cache=False, output_attentions=False):
            query, key, value = attn.c_attn(hidden_states).split(attn.split_size, dim=2)
            query = attn._split_heads(query, attn.num_heads, attn.head_dim)
            key = attn._split_heads(key, attn.num_heads, attn.head_dim)
            value = attn._split_heads(value, attn.num_heads, attn.head_dim)
            past_key, past_value = layer_past
            past_key.index_copy_(2, graph_decoder.position, key)
            past_value.index_copy_(2, graph_decoder.position, value)
            # Small one-query attention on this GTX runs much faster as matrix
            # products than the general memory-efficient attention kernel.
            from torch.nn.attention import sdpa_kernel, SDPBackend
            with sdpa_kernel(SDPBackend.MATH):
                result = torch.nn.functional.scaled_dot_product_attention(query, past_key, past_value,
                            attn_mask=graph_decoder.mask, dropout_p=0.0, is_causal=False)
            result = result.transpose(1, 2).contiguous().view(1, 1, attn.embed_dim)
            return attn.resid_dropout(attn.c_proj(result)), layer_past if use_cache else None, None

        try:
            for block in self.t3.tfmr.h:
                original_forwards.append(block.attn.forward)
                block.attn.forward = types.MethodType(static_attention, block.attn)
            self.reset(past, token)
            stream = torch.cuda.Stream()
            stream.wait_stream(torch.cuda.current_stream())
            with torch.cuda.stream(stream):
                for _ in range(3):
                    self.step()
            torch.cuda.current_stream().wait_stream(stream)
            self.reset(past, token)
            self.graph = torch.cuda.CUDAGraph()
            with torch.cuda.graph(self.graph):
                for _ in range(self.batch):self.step()
            self.reset(past, token)
        finally:
            for block, original in zip(self.t3.tfmr.h, original_forwards):
                block.attn.forward = original

    def decode(self, past, token, stop_token, check=None):
        if self.graph is None:
            self.capture(past, token)
        else:
            self.reset(past, token)
        active=self
        position=past[0][0].shape[-2]
        for index in range(0,1000,self.batch):
            if check:
                check()
            if position+self.batch>=active.capacity:
                bigger=GraphDecoder(self.t3,capacity=min(2048,active.capacity*2),batch=self.batch)
                prefix=tuple(tuple(value[:,:,:position].clone() for value in layer) for layer in active.past)
                bigger.capture(prefix,active.token)
                bigger.seen.copy_(active.seen);bigger.tokens.copy_(active.tokens);bigger.count.copy_(active.count)
                active=bigger;self.t3._speech_graph=bigger
            active.graph.replay();position+=self.batch
            length = index + self.batch + 1
            block = active.tokens[:, max(0, length - self.batch - 1):length]
            if bool((block == stop_token).any()):
                stop = (active.tokens[0, :length] == stop_token).nonzero()[0, 0].item()
                return active.tokens[:, :stop].clone()
        return active.tokens[:, :1001].clone()


def decode_graph(t3, t3_cond, text_tokens, check=None):
    import torch
    from transformers.generation.logits_process import LogitsProcessorList, TemperatureLogitsWarper, TopKLogitsWarper, TopPLogitsWarper, RepetitionPenaltyLogitsProcessor
    start = t3.hp.start_speech_token * torch.ones_like(text_tokens[:, :1])
    embeds, _ = t3.prepare_input_embeds(t3_cond=t3_cond, text_tokens=text_tokens, speech_tokens=start, cfg_weight=0.0)
    output = t3.tfmr(inputs_embeds=embeds, use_cache=True)
    processors = LogitsProcessorList([TemperatureLogitsWarper(0.7), TopKLogitsWarper(1000), TopPLogitsWarper(0.95), RepetitionPenaltyLogitsProcessor(1.2)])
    logits = processors(start, t3.speech_head(output[0][:, -1:])[:, -1, :])
    token = torch.multinomial(torch.softmax(logits, dim=-1), num_samples=1)
    if not hasattr(t3, '_speech_graph'):
        t3._speech_graph = GraphDecoder(t3)
    return t3._speech_graph.decode(output.past_key_values, token, t3.hp.stop_speech_token, check)
