from __future__ import unicode_literals

from dvc.scheme import Schemes
from dvc.utils import LARGE_FILE_SIZE
from dvc.utils.compat import open

import threading
import requests
import logging

from dvc.progress import Tqdm
from dvc.exceptions import DvcException
from dvc.config import Config
from dvc.remote.base import RemoteBASE

logger = logging.getLogger(__name__)


class RemoteHTTP(RemoteBASE):
    scheme = Schemes.HTTP
    REQUEST_TIMEOUT = 10
    CHUNK_SIZE = 2 ** 16
    PARAM_CHECKSUM = "etag"

    def __init__(self, repo, config):
        super(RemoteHTTP, self).__init__(repo, config)

        url = config.get(Config.SECTION_REMOTE_URL)
        self.path_info = self.path_cls(url) if url else None

    def _download(self, from_info, to_file, name=None, no_progress_bar=False):
        request = self._request("GET", from_info.url, stream=True)
        total = self._content_length(request)

        with Tqdm(
            total=total,
            leave=False,
            bytes=True,
            desc_truncate=from_info.url if name is None else name,
            disable=no_progress_bar,
        ) as pbar:
            with open(to_file, "wb") as fd:
                for chunk in request.iter_content(chunk_size=self.CHUNK_SIZE):
                    fd.write(chunk)
                    fd.flush()
                    pbar.update(len(chunk))
            # print completed progress bar for large file sizes
            if (total or pbar.n) > LARGE_FILE_SIZE:
                Tqdm.write(str(pbar))

    def exists(self, path_info):
        return bool(self._request("HEAD", path_info.url))

    def _content_length(self, url_or_request):
        headers = getattr(
            url_or_request,
            "headers",
            self._request("HEAD", url_or_request).headers,
        )
        res = headers.get("Content-Length")
        return int(res) if res else None

    def get_file_checksum(self, path_info):
        url = path_info.url
        headers = self._request("HEAD", url).headers
        etag = headers.get("ETag") or headers.get("Content-MD5")

        if not etag:
            raise DvcException(
                "could not find an ETag or "
                "Content-MD5 header for '{url}'".format(url=url)
            )

        if etag.startswith("W/"):
            raise DvcException(
                "Weak ETags are not supported."
                " (Etag: '{etag}', URL: '{url}')".format(etag=etag, url=url)
            )

        return etag

    def _request(self, method, url, **kwargs):
        kwargs.setdefault("allow_redirects", True)
        kwargs.setdefault("timeout", self.REQUEST_TIMEOUT)

        try:
            return requests.request(method, url, **kwargs)
        except requests.exceptions.RequestException:
            raise DvcException("could not perform a {} request".format(method))

    def gc(self):
        raise NotImplementedError
