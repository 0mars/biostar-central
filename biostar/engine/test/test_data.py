import logging
import os
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.urls import reverse

from biostar.engine import models, views, auth, const
from . import util
from django.conf import settings

TEST_ROOT = os.path.abspath(os.path.join(settings.BASE_DIR, 'export', 'test'))


logger = logging.getLogger('engine')


@override_settings(MEDIA_ROOT=TEST_ROOT)
class DataViewTest(TestCase):

    def setUp(self):
        logger.setLevel(logging.WARNING)

        # Set up generic owner
        self.owner = models.User.objects.create_user(username="test", email="test@l.com")
        self.owner.set_password("test")

        self.project = auth.create_project(user=self.owner, name="test", text="Text", summary="summary",
                                           uid="testing")
        self.project.save()

        # Set up generic data for editing
        self.data = auth.create_data(project=self.project, path=__file__, name="test")

    @patch('biostar.engine.models.Data.save', MagicMock(name="save"))
    def test_data_edit(self):
        "Test Data edit view with POST request"

        data = {'name': "new_data", 'summary': "summary", 'text': "testing",
                'sticky': True}

        url = reverse('data_edit', kwargs=dict(uid=self.data.uid))

        request = util.fake_request(url=url, data=data, user=self.owner)

        response = views.data_edit(request=request, uid=self.data.uid)

        obj = {}
        self.data.fill_dict(obj=obj)

        self.assertTrue("toc" in obj, "Table of content not added during fill_dict()")

        self.process_response(response=response, data=data, save=True)

    @patch('biostar.engine.models.Data.save', MagicMock(name="save"))
    def test_data_upload(self):
        "Test Data upload POST request"

        data = {
            'file': open(__file__, 'r'),
            'summary': 'summary',
            "text": "testing",
            "sticky": True
        }

        url = reverse('data_upload', kwargs=dict(uid=self.project.uid))

        # Create a new user and give them upload access
        user = models.User.objects.create_user(username="test2", email="test2@l.com")
        user.set_password("test")
        user.save()
        access = models.Access(access=models.Access.WRITE_ACCESS,
                               user=user,
                               project=self.project)
        access.save()

        request = util.fake_request(url=url, data=data, user=user)
        response = views.data_upload(request=request, uid=self.project.uid)

        self.process_response(response=response, data=data, save=True)

    def test_add_data(self):
        "Test adding data directory to a project using management commands "

        data_directory = auth.join(__file__, "..", "data")

        data = auth.create_data(project=self.project, path=data_directory)

        self.assertTrue(os.path.exists(data.get_data_dir()), "Directory not being linked")

    def test_data_copy(self):
        "Test data copy interface"

        url = reverse('data_copy', kwargs=dict(uid=self.data.uid))
        clear_url = reverse('clear_clipboard', kwargs=dict(uid=self.project.uid))

        request = util.fake_request(url=url, data={}, method="GET", user=self.owner)
        clear_request = util.fake_request(url=clear_url, data={"board": const.DATA_CLIPBOARD}, method="GET", user=self.owner)

        response = views.data_copy(request=request, uid=self.data.uid)
        clear_response = views.clear_clipboard(request=clear_request, uid=self.project.uid)

        self.process_response(response=response, data={})
        self.process_response(response=clear_response, data={})

    def process_response(self, response, data, save=False):
        "Check the response on POST request is redirected"

        self.assertEqual(response.status_code, 302,
                         f"Could not redirect to project view after testing :\nresponse:{response}")

        if save:
            self.assertTrue( models.Data.save.called, "save() method not called")