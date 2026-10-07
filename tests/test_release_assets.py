"""Keep release binary exceptions narrow while packaging the existing UI textures."""
import importlib.util,json,struct,unittest,zlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release_assets',ROOT/'scripts/build_release.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)

class ReleaseAssetTests(unittest.TestCase):
    def files(self):return {'config.example.json':(ROOT/'config.example.json').read_bytes()}
    def png(self):
        def chunk(name,data):return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data))
        return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xff\x00\x00\xff'))+chunk(b'IEND',b'')
    def test_approved_project_textures_are_allowed(self):
        files=self.files();files['wow-ai/addon/WoWAI/Media/GoblinEye.png']=self.png()
        header=bytearray(18);header[2]=2;header[12:16]=struct.pack('<HH',1,1);header[16]=32
        files['wow-ai/addon/WoWAI/Media/GoblinEye.tga']=bytes(header)+b'\xff\x00\x00\xff'
        release.audit(files)
    def test_unapproved_binary_and_invalid_texture_are_rejected(self):
        for name,body in (('wow-ai/addon/WoWAI/Media/other.png',self.png()),
            ('wow-ai/addon/WoWAI/Media/GoblinEye.png',b'not a PNG'),
            ('wow-ai/addon/WoWAI/Media/GoblinEye.tga',b'invalid')):
            files=self.files();files[name]=body
            with self.subTest(name=name),self.assertRaises(SystemExit):release.audit(files)
    def test_private_paths_in_image_metadata_are_still_rejected(self):
        files=self.files();files['wow-ai/addon/WoWAI/Media/GoblinEye.png']=self.png()+b'C:\\Users\\private\\picture.png'
        with self.assertRaises(SystemExit):release.audit(files)
