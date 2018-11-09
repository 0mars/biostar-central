import logging

import hjson
import os
from django.conf import settings
from django.core.management.base import BaseCommand

from biostar.engine import auth
from biostar.engine.models import Project

logger = logging.getLogger(settings.LOGGER_NAME)


class Bunch():
    def __init__(self, **kwargs):
        self.value = ''
        self.name = self.summary = ''
        self.help = self.type = self.link = ''
        self.__dict__.update(kwargs)



class Command(BaseCommand):
    help = 'Adds data to a project (version 2, will replace current)'

    def add_arguments(self, parser):
        parser.add_argument('--id', default='', help="Select project by primary id")
        parser.add_argument('--uid', default='', help="Select project by unique id")
        parser.add_argument('--path', help="Path to the data to be added (file or directory)")
        parser.add_argument('--text', default='', help="A file containing the description of the data")
        parser.add_argument('--name', default='', help="Sets the name of the data")
        parser.add_argument('--type', default='data', help="Sets the type of the data")

    def handle(self, *args, **options):

        # Collect the parameters.
        id = options['id']
        uid = options['uid']
        path = options['path']
        text = options['text']
        name = options['name']
        type = options['type']

        # Project selection paramter must be set.
        if not (id or uid):
            logger.error(f"Must specify 'id' or 'uid' parameters.")
            return

        # Select project by id or uid.
        if id:
            query = Project.objects.filter(id=id)
        else:
            query = Project.objects.filter(uid=uid)

        # Get the project.
        project = query.first()

        # Project must exist.
        if not project:
            logger.error(f"Project not found! id={id} uid={uid}.")
            return

        # Slightly different course of action on file and directories.
        isfile = os.path.isfile(path)
        isdir = os.path.isdir(path)

        # The data field is empty.
        if not(isfile or isdir):
            logger.error(f"Path is not a file a directory: {path}")
            return

        # Generate alternate names based on input directory type.
        print (f"*** Project: {project.name} ({project.uid})")
        if isdir:
            print(f"*** Linking directory file: {path}")
            altname = os.path.split(path)[0].split(os.sep)[-1]
        else:
            print(f"*** Linking single file: {path}")
            altname = os.path.split(path)[-1]

        # Select the name.
        name = name or altname
        print(f"*** Creating data name: {name}")

        # Create the data.
        auth.create_data(project=project, path=path, type=type, name=name, text=text)
