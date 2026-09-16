from django.contrib.auth import get_user_model
from django.test import TestCase


class ConsoleShellTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user("operator", is_staff=True)
        self.client.force_login(self.staff)

    def test_shell_references_compiled_assets(self):
        response = self.client.get("/console/products")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/static/console/assets/app.js")
        self.assertContains(response, "/static/console/assets/app.css")
        self.assertContains(response, '<div id="root"></div>', html=True)
