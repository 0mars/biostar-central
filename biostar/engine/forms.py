import copy
import shlex
import hjson
import io
import re

from django import forms
from django.template import Template, Context
from django.db.models import Sum
from django.utils.safestring import mark_safe
from django.contrib import messages
from django.urls import reverse
from django.conf import settings
from snowpenguin.django.recaptcha2.fields import ReCaptchaField
from snowpenguin.django.recaptcha2.widgets import ReCaptchaWidget
from biostar.accounts.models import User, Profile
from . import models, auth, factory, util
from .const import *
from .models import Project, Data, Analysis, Job, Access

# Share the logger with models.
logger = models.logger

TEXT_UPLOAD_MAX = 10000

def join(*args):
    return os.path.abspath(os.path.join(*args))


def check_size(fobj, maxsize=0.3):
    # maxsize in megabytes!

    try:
        if fobj and fobj.size > maxsize * 1024 * 1024.0:
            curr_size = fobj.size / 1024 / 1024.0
            msg = f"File too large: {curr_size:0.1f}MB should be < {maxsize:0.1f}MB"
            raise forms.ValidationError(msg)
    except Exception as exc:
        raise forms.ValidationError(f"File size validation error: {exc}")

    return fobj


def check_upload_limit(file, user):
    """
    Checks if the file pushes user over their upload limit."
    """

    # Existing data.
    data = Data.objects.filter(owner=user, method=Data.UPLOAD)

    # The current cumulative size of the current data.
    current_size = data.aggregate(Sum("size"))["size__sum"] or 0

    # The projected size in MB.
    projected_size = file.size + current_size

    # Maximal cumulative sizes.
    max_size = user.profile.max_upload_size * 1024 * 1024

    # Current file size in MB
    file_mb = file.size / 1024 / 1024

    if projected_size > max_size:
        msg = f"You don't have enough storage space for data of size <b>{file_mb:.2f} MB</b>"
        raise forms.ValidationError(mark_safe(msg))

    return file


def clean_file(fobj, user, project, check_name=True):

    if not fobj:
        return fobj

    check_size(fobj=fobj, maxsize=settings.MAX_FILE_SIZE_MB)

    check_upload_limit(file=fobj, user=user)

    # Check if this name already exists.
    if check_name and Data.objects.filter(name=fobj.name, project=project).exists():
        msg = "Name already exists. Upload another file or rename existing data."
        raise forms.ValidationError(msg)

    return fobj


def add_captcha_field(request, fields):
    """Used to dynamically load captcha field into forms"""

    # Trusted users do not need a captcha check
    if request.user.is_authenticated and request.user.profile.trusted:
        return
    # Mutates the fields dict to add captcha field.
    if settings.RECAPTCHA_PRIVATE_KEY:
        fields["captcha"] = ReCaptchaField(widget=ReCaptchaWidget())
    return


class ProjectForm(forms.ModelForm):

    image = forms.ImageField(required=False)

    # Should not edit uid because data directories get recreated

    def __init__(self, request, create=False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.create = create

    class Meta:
        model = Project
        fields = ['name', 'summary', 'text', 'image']

    def clean_image(self):
        cleaned_data = super(ProjectForm, self).clean()
        image = cleaned_data.get('image')
        check_size(fobj=image)

        return image

    def clean(self):
        cleaned_data = super(ProjectForm, self).clean()

        user = self.request.user
        projects = Project.objects.get_all(owner=user)

        # Trusted users can create as many projects
        if user.is_authenticated and (user.is_staff or user.profile.trusted):
            return
        if self.create and projects.count() > settings.MAX_PROJECTS:
            raise forms.ValidationError(f"You have exceeded the maximum of project allowed:{settings.MAX_PROJECTS}.")

        return cleaned_data

    def custom_save(self, owner):
        """Used to save on creation using custom function."""

        name = self.cleaned_data["name"]
        text = self.cleaned_data["text"]
        summary = self.cleaned_data["summary"]
        stream = self.cleaned_data["image"]
        project = auth.create_project(user=owner, name=name, summary=summary, text=text,
                                      stream=stream)
        project.save()

        return project


class DataUploadForm(forms.ModelForm):

    file = forms.FileField(required=False)
    input_text = forms.CharField(max_length=TEXT_UPLOAD_MAX, required=False)
    data_name = forms.CharField(required=False)
    type = forms.CharField(max_length=32, required=False)

    def __init__(self, user, project, *args, **kwargs):
        self.user = user
        self.project = project
        super().__init__(*args, **kwargs)

    def save(self, **kwargs):

        text = self.cleaned_data["text"]
        stream = self.cleaned_data["file"]
        input_text = self.cleaned_data['input_text']
        summary = self.cleaned_data["summary"]
        type = self.cleaned_data["type"]
        name = self.cleaned_data['data_name']

        if stream:
            name = name or stream.name
        else:
            stream = io.StringIO(initial_value=input_text)

        data = auth.create_data(stream=stream, name=name, text=text, user=self.user,
                                project=self.project, summary=summary, type=type)
        if input_text and not self.cleaned_data["file"]:
            Data.objects.filter(pk=data.pk).update(method=Data.TEXTAREA)
            stream.close()

        return data

    class Meta:
        model = Data
        fields = ['data_name', 'file', 'input_text', 'summary', 'text', "sticky", "type"]

    def clean(self):

        cleaned_data = super(DataUploadForm, self).clean()
        upload = cleaned_data.get("file")
        text = cleaned_data.get("input_text")

        if not (upload or text):
            raise forms.ValidationError("Upload a file or write into the text field to create some data.")

        if upload:
            clean_file(fobj=upload, user=self.user,
                       project=self.project, check_name=False)

        else:
            if not cleaned_data.get("data_name"):
                raise forms.ValidationError("Name is required with text inputs.")

        total_count = Data.objects.get_all(owner=self.user).count()
        if total_count >= settings.MAX_DATA:
            raise forms.ValidationError(f"Exceeded maximum amount of data:{settings.MAX_DATA}.")
        return cleaned_data

    def clean_type(self):
        cleaned_data = super(DataUploadForm, self).clean()
        fobj = cleaned_data.get('file')
        if fobj:
            name = fobj.name
        else:
            name = cleaned_data.get('data_name')

        root, ext = os.path.splitext(name)
        ext = ext[1:]
        datatype = EXT_TO_TYPE.get(ext, cleaned_data.get('type'))

        datatype = datatype.upper() or ext.upper()

        return datatype


class DataEditForm(forms.ModelForm):

    type = forms.CharField(max_length=32, required=False)

    def __init__(self, user, *args, **kwargs):

        self.user = user

        super().__init__(*args, **kwargs)

        if self.instance.method == Data.UPLOAD:
            self.fields["file"] = forms.FileField(required=False)

        elif self.instance.method == Data.TEXTAREA:
            initial = ''.join(open(self.instance.get_files()[0], 'r').readlines())
            self.fields["input_text"] = forms.CharField(max_length=TEXT_UPLOAD_MAX,
                                                        required=True,
                                                        initial=initial)

    def save(self, commit=True):

        cleaned_data = super(DataEditForm, self).clean()
        fobj = cleaned_data.get('file')
        input_text = cleaned_data.get("input_text")
        current_file = self.instance.get_files()[0]

        if input_text:
            fobj = io.StringIO(initial_value=input_text)

        if fobj:
            util.write_stream(stream=fobj, dest=current_file)

        return super(DataEditForm, self).save(commit)

    class Meta:
        model = Data
        fields = ['name', 'summary', 'text', 'sticky', "type"]

    def clean_file(self):
        cleaned_data = super(DataEditForm, self).clean()
        return clean_file(fobj=cleaned_data.get('file'),
                          user=self.user,
                          project=self.instance.project,
                          check_name=False)

    def clean_type(self):
        cleaned_data = super(DataEditForm, self).clean()

        datatype = cleaned_data.get('type')

        datatype = datatype.upper()

        return datatype


class RecipeCodeEdit(forms.ModelForm):

    uid = forms.CharField(max_length=32, required=False)

    def __init__(self, user, recipe, *args, **kwargs):
        self.user = user
        self.recipe = recipe
        super().__init__(*args, **kwargs)

    class Meta:
        model = Analysis
        fields = ["template"]

    def clean(self):

        # Check if the user has write access before making changes.
        entry = Access.objects.filter(user=self.user, project=self.recipe.project, access=Access.WRITE_ACCESS).first()
        if entry is None or entry.access != Access.WRITE_ACCESS:
            raise forms.ValidationError("You need write access to change the code.")

    # Turn all input into Unix line ending.
    def clean_template(self):
        cleaned_data = super(RecipeCodeEdit, self).clean()
        template = cleaned_data.get('template')

        template = "\n".join(template.splitlines())
        return template


class RecipeForm(forms.ModelForm):
    image = forms.ImageField(required=False)
    uid = forms.CharField(max_length=32, required=False)


    class Meta:
        model = Analysis
        fields = ["name", "sticky", "image", "summary", "text", "uid"]

    def clean_image(self):
        cleaned_data = super(RecipeForm, self).clean()
        image = cleaned_data.get('image')
        check_size(fobj=image)

        return image

    def clean_uid(self):
        cleaned_data  =  super(RecipeForm, self).clean()
        uid = cleaned_data.get('uid')
        if uid and not uid.isalnum():
            msg = "Only alphanumeric characters allowed, no spaces."
            raise forms.ValidationError(msg)

        return uid


class JobEditForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = ['name', "image", 'text', 'sticky']


class ChangeUserAccess(forms.Form):
    user_id = forms.IntegerField(required=True, widget=forms.HiddenInput())
    project_uid = forms.CharField(required=True, widget=forms.HiddenInput())
    access = forms.IntegerField(initial=Access.NO_ACCESS,
                                widget=forms.Select(choices=Access.ACCESS_CHOICES))

    def save(self):
        "Changes users access to a project"

        user_id = self.cleaned_data["user_id"]
        project_uid = self.cleaned_data["project_uid"]
        user = User.objects.filter(id=user_id).first()
        project = Project.objects.filter(uid=project_uid).first()
        current = Access.objects.filter(user=user, project=project)

        if current:
            current.update(access=self.cleaned_data.get("access", current.first().access))
            return user, current.first()
        new_access = Access(user=user, project=project,
                            access=self.cleaned_data.get("access", Access.NO_ACCESS))
        new_access.save()

        return user, new_access


def access_forms(users, project, exclude=()):
    """Generate a list of forms for a given user list
    Param exclude: a list of users to exclude"""

    forms = []
    for user in users:
        if user in exclude:
            continue
        access = Access.objects.filter(user=user, project=project).first()
        initial = dict(access=Access.NO_ACCESS, user_id=user.id)
        if access:
            initial = dict(access=access.access, user_id=user.id)

        access_form = ChangeUserAccess(initial=initial)
        forms.append((user, access_form))

    return forms


def clean_text(textbox):
    return shlex.quote(textbox)


class RecipeInterface(forms.Form):
    # The name of results when running the recipe.
    # name = forms.CharField(max_length=256, label="Name", help_text="This is how you can identify the run.")

    def __init__(self, request, analysis, json_data, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # The json data determines what fields does the form have.
        self.json_data = json_data

        # The project is required to select data from.
        self.analysis = analysis
        self.project = analysis.project

        # Get request specific information
        self.request = request
        self.user = self.request.user

        # Create the dynamic field from each key in the data.
        for name, data in self.json_data.items():
            field = factory.dynamic_field(data, self.project)

            # Insert only valid fields.
            if field:
                self.fields[name] = field

        add_captcha_field(request=request, fields=self.fields)

    def clean(self):

        # Validate default fields.
        super(RecipeInterface, self).clean()

        if self.user.is_anonymous:
            msg = "You must be logged in."
            raise forms.ValidationError(msg)

        if not auth.authorize_run(user=self.user, recipe=self.analysis):
            msg = "Insufficient permission to execute recipe."
            raise forms.ValidationError(msg)

        if self.analysis.deleted:
            msg = "Can not run a deleted recipe."
            raise forms.ValidationError(msg)

        # Non-staff users have job limits.
        running_jobs = Job.objects.filter(owner=self.user, state=Job.RUNNING)
        if (not self.user.is_staff) and running_jobs.count() >= settings.MAX_RUNNING_JOBS:
            msg = "Exceeded maximum amount of running jobs allowed. Please wait until some finish."
            raise forms.ValidationError(msg)

        self.validate_text_fields()

    def validate_text_fields(self):
        """Validate Character fields """

        # Default pattern matches any alphanumeric string with a given length
        default_pattern = r"^\w{1,10}$"

        for field in self.json_data:
            val = self.cleaned_data.get(field)

            # Validate text fields
            if (val is None) or (self.json_data[field].get("display") != TEXTBOX):
                continue

            # Acceptable regex pattern
            regex_pattern = self.json_data[field].get("regex", default_pattern)

            if re.fullmatch(regex_pattern, val) is None:
                msg = f"{field} : contains invalid patterns. Valid pattern:{regex_pattern}."
                raise forms.ValidationError(msg)

    def fill_json_data(self):
        """
        Produces a filled in JSON data based on user input.
        Should be called after the form has been filled and is valid.
        """

        # Creates a data.id to data mapping.
        store = dict((data.id, data) for data in self.project.data_set.all())

        # Make a copy of the original json data used to render the form.
        json_data = copy.deepcopy(self.json_data)

        # Alter the json data and fill in the extra information.
        for field, item in json_data.items():

            # If the field is a data field then fill in more information.
            if item.get("source") == "PROJECT":
                data_id = int(self.cleaned_data.get(field))
                data = store.get(data_id)
                # This mutates the `item` dictionary!
                data.fill_dict(item)
                continue

            # The JSON value will be overwritten with the selected field value.
            if field in self.cleaned_data:
                value = self.cleaned_data[field]
                # Clean the textbox value
                item["value"] = value if item['display'] != TEXTBOX else clean_text(value)

        return json_data


class EditCode(forms.Form):
    SAVE = "SAVE"

    # Determines what action to perform on the form.
    action = forms.CharField()

    # The script template.
    template = forms.CharField(required=False)

    # The json specification.
    json = forms.CharField(required=False)

    def __init__(self, user, project, *args, **kwargs):
        self.user = user
        self.project = project
        super().__init__(*args, **kwargs)

    def clean_json(self):
        cleaned_data = super(EditCode, self).clean()
        json_text = cleaned_data.get("json")
        try:
            hjson.loads(json_text)
        except Exception as exc:
            msg = f"Invalid json: {exc}"
            raise forms.ValidationError(msg)
        return json_text

    def clean(self):
        cleaned_data = super(EditCode, self).clean()
        action = cleaned_data.get("action")

        if action == self.SAVE:

            if self.user.is_anonymous:
                msg = "Anonymous users may not save the form."
                raise forms.ValidationError(msg)

            # Write access to the object.
            allow = Access.objects.filter(user=self.user, project=self.project, access=Access.WRITE_ACCESS).exists()

            # Conditions of when we allow the save.
            allow = allow or self.user.is_staff

            if not allow:
                msg = "Anonymous users may not save the form."
                raise forms.ValidationError(msg)
