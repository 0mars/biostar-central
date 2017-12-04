'''
This is active only when deployed via UWSGI
'''

import logging, time, shutil, subprocess
from django.core import management
from django.utils.text import force_text
import time

logger = logging.getLogger("engine")

HAS_UWSGI = False

def int_to_bytes(value):
    return (value).to_bytes(8, byteorder='big')

def int_from_bytes(args, name):
    return int.from_bytes(args[name].encode(), byteorder='big')

COUNTER = 1

try:
    from uwsgidecorators import *

    HAS_UWSGI = True

    @timer(20)
    def timer(args):
        from biostar.engine.models import Job
        # Check for queued jobs.
        jobs = Job.objects.filter(state=Job.QUEUED)
        if jobs:
            # Put the jobs in SPOOLED state so that it does not get respooled.
            Job.objects.filter(state=Job.QUEUED).update(state=Job.SPOOLED)
            for job in jobs:
                logger.info(f"Spooling job id={job.id}")
                execute_job.spool(job_id=job.id)

    #@timer(10)
    def spool_demo(args):
        """
        Spooling demo scheduler. Comment out the decorator to launch.
        """
        global COUNTER
        logger.info(f"SPOOL DEMO SUBMIT {COUNTER}, {COUNTER+1}, {COUNTER+2}")
        spool_demo_task.spool(value=COUNTER)
        spool_demo_task.spool(value=COUNTER + 1)
        spool_demo_task.spool(value=COUNTER + 2)
        COUNTER += 3

    @spool(pass_arguments=True)
    def spool_demo_task(value):
        '''
        Spool demonstration task.
        '''
        N = 5
        logger.info(f"-> JOB START {value} ")
        time.sleep(N)
        logger.info(f"<- JOB END {value}")

    @spool(pass_arguments=True)
    def execute_job(job_id):
        """
        Execute job in spooler.
        """
        logger.info(f"Executing spooled job id={job_id}")
        management.call_command('job', id=job_id)

    @spool
    def unpack(args):
        #data_id = int_from_bytes(args, "data_id")
        #unpacker(data_id=data_id)
        pass

    @spool
    def copy(args):
        pass
        #return


except ModuleNotFoundError as exc:

    # No spooling same interface.
    def unpack(data_id):
        unpacker(data_id=data_id)


def execute(command, workdir="."):
    proc = subprocess.run(command, cwd=workdir, shell=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = force_text(proc.stdout), force_text(proc.stderr)
    return stdout, stderr


def unpacker(data_id):
    """
    Unpacks a data and sets the status to READY.
    """
    from biostar.engine.models import Data
    query = Data.objects.filter(id=data_id)
    data = query.first()
    query.update(state=Data.PENDING)
    command = f'tar xzvf {data.file.path}'
    try:
        stdout, stderr = execute(command=command, workdir=data.get_data_dir())
        logger.info(f'Data id={data_id} has been unpacked')
        query.update(state=Data.READY)
    except Exception as exc:
        logger.error(f"Error: f{exc}")
        query.update(state=Data.ERROR)


def copier(source=None, target_data=None, target_project=None, fname=None, link=False):

    """
    Copies source data to target_data id. or adds a fname to target_project id
    """
    from biostar.engine.models import Data, Project
    from biostar.engine import auth

    assert (source and target_data) or (target_project and fname)

    source = Data.objects.filter(id=source).first()
    target_data = Data.objects.filter(id=target_data).first()
    project = Project.objects.filter(id=target_project).first()

    if project:
        assert fname
        auth.create_data(project=project, path=fname, link=link)
        return

    if source:
        assert target_data

    # Copying just links source to target (for now)
    target_data.link = source.get_path()
    target_data.save()

