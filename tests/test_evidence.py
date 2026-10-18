import unittest
from unittest.mock import Mock

from bot.utils.evidence import validate_elevation, validate_proof
from bot.utils.location import LocationLookupError, LocationResolver, local_label


class EvidenceTests(unittest.TestCase):
    def test_elevation_optional_and_range(self):
        self.assertIsNone(validate_elevation(None))
        self.assertEqual(validate_elevation(0), 0)
        self.assertEqual(validate_elevation(420), 420)
        for value in (-1, 20001):
            with self.assertRaises(ValueError):
                validate_elevation(value)

    def test_image_validation(self):
        valid = Mock(content_type="image/png", size=1024)
        validate_proof(valid)
        for bad in [
            Mock(content_type="application/pdf", size=100),
            Mock(content_type="image/jpeg", size=11 * 1024 * 1024),
            Mock(content_type=None, size=100),
        ]:
            with self.assertRaises(ValueError):
                validate_proof(bad)

    def test_locality_drops_street_and_house(self):
        address = {
            "house_number": "51", "road": "Private Street", "suburb": "Ras Beirut",
            "city": "Beirut", "country": "Lebanon",
        }
        result = local_label(address)
        self.assertEqual(result, "Ras Beirut, Beirut, Lebanon")
        self.assertNotIn("Private Street", result)


class DisabledResolverTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_lookup_and_optional_blank(self):
        from classes.database import Database
        db = Database(":memory:")
        await db.create_tables()
        try:
            resolver = LocationResolver(db)
            resolver.user_agent = ""
            self.assertIsNone(await resolver.resolve(None))
            self.assertIsNone(await resolver.resolve(" "))
            with self.assertRaises(LocationLookupError):
                await resolver.resolve("Beirut, Lebanon")
        finally:
            await db.close()
