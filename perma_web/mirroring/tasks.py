import json
import os
import os.path
import tempfile
import zipfile
from celery import shared_task
import requests
import tempdir

from django.core.files.storage import default_storage
from django.core.urlresolvers import reverse
from django.conf import settings
from django.shortcuts import get_object_or_404

from perma.models import Asset, Link
from perma.tasks import create_storage_dir

from .utils import serialize_datetime, unserialize_datetime


@shared_task
@tempdir.run_in_tempdir()
def compress_link_assets(*args, **kwargs):
    """
    This task creates a zipfile containing the assets of a given Perma
    link. The zip file does *not* contain mutable status data about
    the link (e.g. whether it's vested or not), only immutable asset
    metadata.  This is a Celery task so that it can be run after the
    tasks that generate the assets are finished, which we arrange for
    by means of a chord. Thus, the first positional arguments of this
    function will be return value of those tasks. We thus don't rely
    on positional arguments and retrieve all of our arguments via
    kwargs.
    """
    # fetch link and asset
    try:
        guid = kwargs['guid']
    except KeyError:
        raise TypeError("compress_link_assets() requires a guid keyword argument")
    target_link = get_object_or_404(Link, guid=guid)
    target_asset = get_object_or_404(Asset, link=target_link)

    # build metadata
    metadata = {
        "guid": guid,
        "submitted_url": target_link.submitted_url,
        "creation_timestamp": serialize_datetime(target_link.creation_timestamp),
        "submitted_title": target_link.submitted_title,
    }

    # Here we are going to open a temporary file to store our zip data to.
    # Because of @run_in_tempdir we have already chdir'd to a temp dir.
    # Next we will use default_storage to copy each file in target_asset.base_storage_path
    # (which may come from the local disk or a remote location like S3)
    # to the temp dir, and then from there into the open zip file.
    temp_file = tempfile.TemporaryFile()
    with zipfile.ZipFile(temp_file, "w") as zipfh:
        for root, dirs, files in default_storage.walk(target_asset.base_storage_path):
            # root will be relative to MEDIA_ROOT
            create_storage_dir(root)
            for file in files:
                file_path = os.path.join(root, file)

                # copy from default_storage to local temp dir
                with default_storage.open(file_path, 'rb') as source:
                    with open(file_path, 'wb') as dest:
                        dest.write(source.read())

                # write to zip
                zipfh.write(file_path)
        zipfh.writestr(os.path.join(guid, "metadata.json"),
                       json.dumps(metadata))

    # now our zip file has been written, we can store it to default_storage
    temp_file.seek(0)
    zipfile_storage_path = os.path.join(settings.MEDIA_ARCHIVES_ROOT, target_asset.base_storage_path+".zip")
    default_storage.store_file(temp_file, zipfile_storage_path, overwrite=True)


@shared_task
@tempdir.run_in_tempdir()
def update_perma(link_guid):
    """
    Update the vested/darchived status of a perma link, and download the
    assets if necessary
    """
    # N.B. This function has two instances of downloading stuff from
    # the root server using a scheme that looks something like
    #    settings.SERVER + reverse("url_pattern")
    # This is nice because it means we don't have to repeat our URL
    # patterns from urls.py, but it hardcodes the fact that the root
    # server is another Perma instance. It's unclear to me which is a
    # better fact to abstract, but this is easier for now.

    ## First, let's get the metadata for this link. The metadata
    ## contains information about where we should place the assets (if
    ## we decide that we need them). This is also a fast check to make
    ## sure the link GUID is actually real.
    metadata_server = settings.ROOT_METADATA_SERVER
    metadata_url = metadata_server + reverse("service_link_status", args=(link_guid,))
    metadata = requests.get(metadata_url).json()

    ## Next, let's see if we need to get the assets. If we have the
    ## Link object for this GUID, we're going to assume we already
    ## have what we need. It would make a little more sense to use the
    ## Asset object here instead, but we're definitely going to need
    ## to do stuff to the Link object so we might as well get that
    ## instead. In practice they should be ~one to one.
    try:
        link = Link.objects.get(guid=link_guid)
    except Link.DoesNotExist:
        ## We need to download the assets. We can download an archive
        ## from the assets server.
        assets_server = settings.ROOT_ASSETS_SERVER
        assets_url = assets_server + reverse("mirroring:link_assets", args=(link_guid,))

        # Temp paths can be relative because we're in run_in_tempdir()
        temp_zip_path = 'temp.zip'
        temp_unzipped_files_path = 'files/'

        # Save remote zip file to disk, using streaming to avoid keeping large files in RAM.
        request = requests.get(assets_url, stream=True)
        with open(temp_zip_path, 'wb') as f:
            for chunk in request.iter_content(1024):
                f.write(chunk)

        ## Extract the archive and change into the extracted folder.
        with zipfile.ZipFile(temp_zip_path, "r") as zipfh:
            #assets_path = os.path.dirname(os.path.join(settings.MEDIA_ROOT, metadata["path"]))
            zipfh.extractall(temp_unzipped_files_path)
        os.chdir(temp_unzipped_files_path)

        # Save all extracted files to default_storage, using the path in metadata.
        for root, dirs, files in os.walk('.'):
            for file in files:
                source_file_path = os.path.join(root, file)
                dest_file_path = source_file_path
                with open(source_file_path, 'rb') as source_file:
                    default_storage.store_file(source_file, dest_file_path)

        ## We can now get some additional metadata that we'll need to
        ## create the Link object.
        with open(os.path.join(link_guid, "metadata.json"), "r") as fh:
            link_metadata = json.load(fh)

        ## We now have everything we need to initialize the Link object.
        link = Link(guid=link_guid)
        link.submitted_url = link_metadata["submitted_url"]
        link.submitted_title = link_metadata["submitted_title"]
        link.created_by = None # XXX maybe we should do something with FakeUser here
        link.save(pregenerated_guid=True) # We need to save this so that we can create an Asset object

        # This is a stupid hack to overcome the fact that the Link has
        # auto_now_add=True, so it's always going to be saved to the
        # current time on first creation.
        link.creation_timestamp = unserialize_datetime(link_metadata["creation_timestamp"])
        link.save()

        ## Lastly, let's create an Asset object for this Link.
        asset = Asset(link=link)
        asset.base_storage_path = metadata["path"]
        asset.image_capture = metadata["image_capture"]
        asset.warc_capture = metadata["source_capture"]
        asset.pdf_capture = metadata["pdf_capture"]
        asset.text_capture = metadata["text_capture"]
        asset.save()

    ## We can now add some of the data we got from the metadata to the Link object
    link.dark_archived = metadata["dark_archived"]
    link.vested = metadata["vested"]
    link.save()


@shared_task
def poke_mirrors(*args, **kwargs):
    try:
        link_guid = kwargs['link_guid']
    except KeyError:
        raise TypeError("poke_mirrors() requires a link_guid keyword argument")
    for mirror in settings.MIRRORS:
        requests.get(mirror + reverse("mirroring:update_link", args=(link_guid,)))

