'use strict';
require('./runtime-storage').activate();
// Goblin Eye background worker. No addon files, capture, chat queue or game APIs.
// The transport sends explicit requests and receives display state over pipes.
const {SpeechManager} = require('./speech');
const {ModelCatalog} = require('./models');
const readline = require('readline');
let speech, catalog, timer;
const send = message => { if (!process.stdout.destroyed) process.stdout.write(JSON.stringify(message) + '\n'); };
function snapshot() {
  if (speech && catalog) send({state: {speech: speech.info(), catalogs: catalog.wire(), cache: [...catalog.cache]}});
}
const input = readline.createInterface({input: process.stdin});
input.on('line', async line => {
  let message;
  try { message = JSON.parse(line); }
  catch { return; }
  const {id, method, args = []} = message;
  try {
    if (method === 'start') {
      const options = args[0];
      speech = new SpeechManager({directory: options.directory, onChange: snapshot,
        log: (...parts) => send({log: parts})});
      catalog = new ModelCatalog({config: options.config, defaultAgent: options.config.agent,
        cwd: options.cwd, onChange: snapshot});
      if (options.background) {
        if (catalog.backgroundEnabled) {
          void catalog.refreshBackground();
          timer = setInterval(() => void catalog.refreshBackground(), 10000);
        }
        if (speech.neural?.prewarm === true && speech.settings.profile !== 'desktop') speech.warm();
      }
    } else if (method === 'voice.control') {
      speech.control(args[0], args[1], () => args[2]);
    } else if (method === 'voice.completed') {
      try { speech.completed(args[0]); }
      catch (error) { speech.error = error.message; speech.changed(); }
    } else if (method === 'models.request') {
      await catalog.request(args[0]);
    } else if (method === 'models.forget') {
      catalog.views.delete(args[0]);
    } else throw Error('Unknown companion request.');
    snapshot();
    send({id, ok: true});
  } catch (error) { send({id, error: error.message}); }
});
input.on('close', () => { clearInterval(timer); catalog?.close(); speech?.stop(); process.exit(0); });
