import hjson
import logging

from django.conf import settings
from django.core.management.base import BaseCommand

from biostar.engine import auth
from biostar.engine.models import Project, DataType

logger = logging.getLogger(settings.LOGGER_NAME)


class Bunch():
    def __init__(self, **kwargs):
        self.value = ''
        self.name = self.summary = ''
        self.text = self.type = self.link = ''
        self.__dict__.update(kwargs)


class Command(BaseCommand):
    help = 'Adds data to a project'

    def add_arguments(self, parser):
        parser.add_argument('--id', default=0, help="Select project by primary id")
        parser.add_argument('--uid', default="hello", help="Select project by unique id")
        parser.add_argument('--path', help="The path to the data", default='')
        parser.add_argument('--summary', help="Summary for the data", default='No summary')
        parser.add_argument('--name', help="Name for the data", default='')
        parser.add_argument('--type', help="Data type", default='')

        parser.add_argument('--json', help="Reads data specification from a json file", default='')

    def handle(self, *args, **options):

        id = options['id']
        uid = options['uid']
        path = options['path'].rstrip("/")
        name = options['name']
        summary = options['summary']
        data_type = options['type']

        json = options['json']

        # Select project by id or uid.
        if id:
            query = Project.objects.filter(id=id)
        else:
            query = Project.objects.filter(uid=uid)

        # Get the project.
        project = query.first()

        # Project must exist.
        if not project:
            logger.error(f"Project does not exist: id={id} uid={uid}")
            return

        # Reads a file directly or a spec.
        if not (path or json):
            logger.error(f"Must specify a value for --path --link or --json")
            return

        if json:
            # There 'data' field of the spec has the files.
            json_data = hjson.load(open(json))
            json_data = json_data.get('data', [])
            data_list = [Bunch(**row) for row in json_data]
        else:
            # There was one data loading request.
            data_list = [
                Bunch(type=data_type, value=path, name=name, summary=summary, text='')
            ]

        # Add each collected datatype.
        for bunch in reversed(data_list):
            # Get the right datatype.
            type_value = DataType.objects.filter(project=project, symbol=bunch.type).first()

            if data_type and not type_value:
                logger.warning(f"Invalid data type: {bunch.type}")

            auth.create_data(project=project, path=bunch.value,
                             data_type=bunch.type,
                             name=bunch.name,
                             summary=bunch.summary, text=bunch.text)
