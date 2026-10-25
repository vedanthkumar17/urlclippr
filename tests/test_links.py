import string
import unittest

from fastapi.testclient import TestClient

from main import app


class LinksApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_create_link(self):
        response = self.client.post(
            "/links",
            json={"url": "https://example.com/some/path"},
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(
            set(body),
            {"original_url", "short_code", "short_url"},
        )
        self.assertEqual(body["original_url"], "https://example.com/some/path")
        self.assertEqual(len(body["short_code"]), 6)
        self.assertTrue(
            all(character in string.ascii_letters + string.digits for character in body["short_code"])
        )
        self.assertEqual(
            body["short_url"],
            f"http://testserver/{body['short_code']}",
        )

    def test_invalid_url_is_rejected(self):
        response = self.client.post("/links", json={"url": "not-a-url"})

        self.assertEqual(response.status_code, 422)

    def test_short_codes_are_unique(self):
        short_codes = set()

        for index in range(25):
            response = self.client.post(
                "/links",
                json={"url": f"https://example.com/page/{index}"},
            )

            self.assertEqual(response.status_code, 201)
            short_codes.add(response.json()["short_code"])

        self.assertEqual(len(short_codes), 25)


if __name__ == "__main__":
    unittest.main()
