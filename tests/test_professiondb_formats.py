"""Synthetic regression coverage for ProfessionDB 1.9 literal metadata."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from goblin_eye.ingestion.alts_forever import AltsForeverAdapter
from goblin_eye.ingestion.lua_literals import read_library_table
from goblin_eye.ingestion.professiondb import ProfessionDBAdapter, parse_professiondb
from goblin_eye.item_graph import ItemGraph
from goblin_eye.repository import Database

ROOT = Path(__file__).resolve().parents[1]


class ProfessionDBFormatTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'ProfessionDB'
        self.core = self.root / 'Data/Forever/_core'
        self.locale = self.root / 'Data/Forever/enUS'
        self.core.mkdir(parents=True)
        self.locale.mkdir()
        self.db = Database(Path(self.temp.name) / 'test.db')
        self.db.migrate(ROOT / 'migrations')

    def addon(self, *, modern=True):
        files = ['Alchemy', 'RecipeItems', 'AcquireMethods']
        if modern:
            files += ['HiddenRecipes', 'Sources', 'SourceNames', 'VendorSources']
        (self.root / 'ProfessionDB_Camelot.toc').write_text(
            '## Interface: 16001\n## Version: ProfessionDB-v1.9.0\n' +
            ''.join(f'Data/Forever/_core/{name}.lua\n' for name in files) +
            'Data/Forever/enUS/Alchemy.lua\n', encoding='utf-8')
        (self.root / 'LICENSE').write_text('MIT License\nSynthetic fixture.', encoding='utf-8')
        (self.core / 'RecipeItems.lua').write_text('lib:LoadRecipeItems({})\nlib:LoadSkillRankBooks({})', encoding='utf-8')
        (self.core / 'AcquireMethods.lua').write_text('lib:LoadAcquireMethods({[101]=1})', encoding='utf-8')
        if modern:
            for name in files[3:]:
                (self.core / f'{name}.lua').write_text('-- Metadata source document; not a recipe table.\n', encoding='utf-8')
        source = ('-- WoW Forever\n-- build 1.60.1.69977 - 2 recipes\n'
                  'if not lib:IsGameVersion("Forever") then return end\n'
                  'lib:LoadCore(171, {\n'
                  '[101]={craftedItemId=201,teaches=101,requiredSkill=50,reagents={[301]=2}},\n'
                  '[102]={craftedItemId=202,teaches=102,requiredSkill=75,reagents={[302]=1}}\n'
                  '})\n')
        if modern:
            source += 'lib:LoadBorrowed("requiredSkill", "Vanilla", {101})\n'
        (self.core / 'Alchemy.lua').write_text(source, encoding='utf-8')
        (self.locale / 'Alchemy.lua').write_text(
            'lib:LoadNames(171,{[101]={name="Fixture potion"},[102]={name="Fixture elixir"}})', encoding='utf-8')

    def test_modern_borrowed_skills_and_extra_catalogs_preserve_provenance(self):
        self.addon()
        dataset = parse_professiondb(self.root)
        self.assertEqual(len(dataset.recipes), 2)
        self.assertEqual(dataset.recipes[0].attributes['borrowed_fields'], {'requiredSkill': 'Vanilla'})
        self.assertEqual(dataset.recipes[0].attributes['required_skill_basis'], 'borrowed:Vanilla')
        self.assertNotIn('borrowed_fields', dataset.recipes[1].attributes)
        self.assertIn('Data/Forever/_core/Sources.lua', dataset.files)
        result = ProfessionDBAdapter().import_file(self.db, self.root)
        self.assertEqual(result.records, 2)
        with self.db.transaction() as c:
            row = c.execute('SELECT skill_required,attributes_json FROM recipe_facts WHERE spell_id=101').fetchone()
            self.assertEqual(row['skill_required'], 50)
            self.assertEqual(json.loads(row['attributes_json'])['required_skill_basis'], 'borrowed:Vanilla')
            self.assertEqual(c.execute('SELECT COUNT(*) FROM acquisition_facts').fetchone()[0], 0)
        self.assertEqual(ProfessionDBAdapter().import_file(self.db, self.root).records, 0)

    def test_older_catalog_without_borrowed_calls_still_imports(self):
        self.addon(modern=False)
        dataset = parse_professiondb(self.root)
        self.assertEqual(len(dataset.recipes), 2)
        self.assertTrue(all('borrowed_fields' not in r.attributes for r in dataset.recipes))

    def test_core_item_ids_do_not_override_recipe_items(self):
        self.addon()
        core = self.core / 'Alchemy.lua'
        core.write_text(core.read_text().replace('craftedItemId=201,', 'craftedItemId=201,itemId=401,')
                        .replace('craftedItemId=202,', 'craftedItemId=202,itemId=402,'), encoding='utf-8')
        (self.core / 'RecipeItems.lua').write_text(
            'lib:LoadRecipeItems({[101]=501})\nlib:LoadSkillRankBooks({})', encoding='utf-8')

        ProfessionDBAdapter().import_file(self.db, self.root)
        with self.db.transaction() as c:
            rows = c.execute('SELECT attributes_json FROM recipe_facts ORDER BY spell_id').fetchall()
            teaching = c.execute('SELECT item_id,raw_reference FROM recipe_teaching_items').fetchall()
        self.assertEqual([tuple(row) for row in teaching], [(501, 'Data/Forever/_core/RecipeItems.lua#101')])
        discrepancies = [json.loads(row['attributes_json'])['teaching_item_discrepancy'] for row in rows]
        self.assertEqual([row['core_item_id'] for row in discrepancies], [401, 402])
        self.assertEqual([row['recipe_items_item_id'] for row in discrepancies], [501, None])

    def test_learning_plan_recognizes_lowercase_recipe_with_zero_difficulty(self):
        self.addon()
        ProfessionDBAdapter().import_file(self.db, self.root)
        save = Path(self.temp.name) / 'AltsForever.lua'
        save.write_text('AltsForeverDB={v=2,chars={Fixture={name="Fixture",class="MAGE",level=5,'
                        'recipes={Alchemy={["fixture potion"]=0,["Fixture elixir"]=true}}}}}', encoding='utf-8')
        self.assertEqual(AltsForeverAdapter().import_file(self.db, save).snapshots, 1)
        with self.db.transaction() as c:
            snapshot = c.execute('SELECT id,payload_json FROM character_snapshots').fetchone()
            fact_ids = [row['id'] for row in c.execute('SELECT id FROM recipe_facts')]
        self.assertEqual(json.loads(snapshot['payload_json'])['character']['recipes']['Alchemy']['fixture potion'], 0)
        for fact_id in fact_ids:
            plan = ItemGraph(self.db).recipe(fact_id, snapshot['id'])['learning_plan']
            self.assertEqual(plan['character']['learned_recipe_status'], 'recorded_known')

    def test_applied_enchants_and_recipe_enchants_are_queryable(self):
        self.addon()
        path=self.core/'Alchemy.lua'
        text=path.read_text().replace('craftedItemId=201,','craftedItemId=201,enchantId=254,enchantSlot="CHEST",stats={ITEM_MOD_STAMINA_SHORT=4},')
        path.write_text(text+'lib:LoadEnchantsCore({[723]={slots={"TWOHAND"},stats={ITEM_MOD_INTELLECT_SHORT=5}}})\n')
        with (self.locale/'Alchemy.lua').open('a') as f:
            f.write('\nlib:LoadEnchantsNames({[723]={name="Fixture intellect enchant"}})')
        ProfessionDBAdapter().import_file(self.db,self.root)
        from goblin_eye.item_properties import ItemProperties
        self.assertEqual(ItemProperties(self.db).enchant(254)['applications'][0]['stats'],{'stamina':4})
        self.assertEqual(ItemProperties(self.db).enchant(723)['applications'][0]['stats'],{'intellect':5})
        self.assertEqual(ItemProperties(self.db).enchant(999999)['status'],'not_recorded')
        self.assertFalse(ItemProperties(self.db).enchant(254)['numeric_conflict'])

    def test_borrowed_annotations_can_precede_or_follow_enchant_metadata(self):
        for suffix in ('lib:LoadEnchantsCore({})\nlib:LoadBorrowed("requiredSkill","Vanilla",{101})',
                       'lib:LoadBorrowed("requiredSkill","Vanilla",{101})\nlib:LoadEnchantsCore({})'):
            borrowed = {}
            profession, rows = read_library_table('lib:LoadCore(333,{[101]={requiredSkill=50}})\n' + suffix,
                'LoadCore', True, ('LoadEnchantsCore', 'LoadBorrowed'), borrowed)
            self.assertEqual(profession, 333)
            self.assertEqual(rows[101]['requiredSkill'], 50)
            self.assertEqual(borrowed, {101: {'requiredSkill': 'Vanilla'}})

    def test_unreviewed_or_executable_trailing_data_is_rejected(self):
        prefix = 'lib:LoadCore(171,{[101]={requiredSkill=50}})\n'
        for suffix in ('os.execute("bad")', 'lib:Unknown({})',
                       'lib:LoadBorrowed("requiredSkill",os.execute("bad"),{101})',
                       'lib:LoadBorrowed("requiredSkill","Vanilla",{os.execute("bad")})',
                       'lib:LoadBorrowed("requiredSkill","Vanilla",{999})',
                       'lib:LoadBorrowed("requiredSkill","Vanilla",{101,101})',
                       'lib:LoadBorrowed("sources","Vanilla",{101})',
                       'lib:LoadBorrowed("requiredSkill","",{101})',
                       'lib:LoadBorrowed("requiredSkill","Vanilla",{[2]=101})'):
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                read_library_table(prefix + suffix, 'LoadCore', True, ('LoadBorrowed',), {})

    def test_bad_update_leaves_existing_recipe_dataset_untouched(self):
        self.addon()
        ProfessionDBAdapter().import_file(self.db, self.root)
        before = parse_professiondb(self.root).fingerprint
        with (self.core / 'Alchemy.lua').open('a', encoding='utf-8') as file:
            file.write('lib:LoadBorrowed("requiredSkill","Vanilla",{999})\n')
        with self.assertRaises(ValueError):
            ProfessionDBAdapter().import_file(self.db, self.root)
        with self.db.transaction() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM recipe_facts').fetchone()[0], 2)
            self.assertEqual(c.execute('SELECT sha256 FROM research_datasets WHERE active=1').fetchone()[0], before)


if __name__ == '__main__':
    unittest.main()
