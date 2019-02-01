import logging,os
from django.test import TestCase, override_settings
from unittest.mock import patch, MagicMock
from django.core import management
from django.urls import reverse
from django.conf import settings
from biostar.engine import auth
from biostar.engine import models, views

from . import util

logger = logging.getLogger('engine')

TEST_ROOT = os.path.abspath(os.path.join(settings.BASE_DIR, 'export', 'tested'))


@override_settings(MEDIA_ROOT=TEST_ROOT)
class JobViewTest(TestCase):

    def setUp(self):
        logger.setLevel(logging.WARNING)

        # Set up generic owner
        self.owner = models.User.objects.create_user(username=f"tested{util.get_uuid(10)}", email="tested@l.com")
        self.owner.set_password("tested")

        self.project = auth.create_project(user=self.owner, name="tested", text="Text", summary="summary",
                                           uid="tested")

        self.recipe = auth.create_analysis(project=self.project, json_text="{}", template="",
                                           security=models.Analysis.AUTHORIZED)

        self.job = auth.create_job(analysis=self.recipe, user=self.owner)
        self.job.save()



    @patch('biostar.engine.models.Job.save', MagicMock(name="save"))
    def test_job_edit(self):
        "Test job edit with POST request"

        data = {'name':'tested', 'text':"tested", 'sticky':True}
        url  = reverse('job_edit', kwargs=dict(uid=self.job.uid))

        request = util.fake_request(url=url, data=data, user=self.owner)

        response = views.job_edit(request=request, uid=self.job.uid)
        self.process_response(response=response, data=data, save=True)

    def test_job_runner(self):
        "Testing Job runner using management command"

        management.call_command('job', id=self.job.id, verbosity=2)
        management.call_command('job', list=True)


    def test_job_serve(self):
        "Test file serve function."
        from django.http.response import FileResponse

        management.call_command('job', id=self.job.id)

        url = reverse('job_view', kwargs=dict(uid=self.job.uid))

        data = {"paths":"runlog/input.json"}

        request = util.fake_request(url=url, data=data, user=self.owner)

        response = views.job_serve(request=request, uid=self.job.uid, path=data["paths"])

        self.assertTrue(isinstance(response, FileResponse), "Response is not a file.")


    def process_response(self, response, data, save=False):
        "Check the response on POST request is redirected"

        self.assertEqual(response.status_code, 302,
                         f"Could not redirect to project view after tested :\nresponse:{response}")

        if save:
            self.assertTrue( models.Job.save.called, "save() method not called")