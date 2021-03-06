# -*- coding: utf-8 -*-

import os
import time
import pickle
import logging
import datetime

from django.core.files.storage import Storage
from tempfile import TemporaryFile

from boto import connect_s3
from boto.s3.connection import Location
from boto.exception import S3CreateError, S3ResponseError

logger = logging.getLogger(__name__)

class S3Storage(Storage):

	def __init__(self, bucket_name=None, key=None, secret=None, location=None,
		host=None, policy=None, replace=True):

		self.bucket_name = bucket_name if bucket_name else settings.BOTO_S3_BUCKET
		self.key = key if key else settings.AWS_ACCESS_KEY_ID
		self.secret = secret if secret else settings.AWS_SECRET_ACCESS_KEY
		self.location = location if location else settings.BOTO_BUCKET_LOCATION
		self.host = host if host else settings.BOTO_S3_HOST
		self.policy = policy if policy else settings.AWS_ACL_POLICY
		self.replace = replace

		self.location = getattr(Location, self.location)

		self._bucket = None

	@property
	def bucket(self):
		if not self._bucket:
			self.s3 = connect_s3(aws_access_key_id=self.key, aws_secret_access_key=self.secret, host=self.host)

			try:
				self._bucket = self.s3.create_bucket(self.bucket_name, location=self.location, policy=self.policy)
			except (S3CreateError, S3ResponseError):
				self._bucket = self.s3.get_bucket(self.bucket_name)
		return self._bucket

	def delete(self, name):
		self.bucket.new_key(name).delete()

	def exists(self, name):
		return self.bucket.new_key(name).exists()

	def _list(self, path):
		result_list = self.bucket.list(path, '/')

		for key in result_list:
			yield key.name

	def listdir(self, path):
		return [], self._list(path)

	def size(self, name):
		return self.bucket.lookup(name).size

	def url(self, name, expires=30, query_auth=False, force_http=False):
		"""
		URL for file downloading.
		"""
		key = self.bucket.get_key(name.encode('utf-8'))
		return key.generate_url(expires, query_auth=query_auth, force_http=force_http)

	def _open(self, name, mode='rb'):
		"""
		Open file.
		"""
		result = TemporaryFile()
		self.bucket.get_key(name).get_file(result)

		return result

	def _save(self, name, content):
		"""
		Save file.
		"""
		key = self.bucket.new_key(name)
		content.seek(0)

		if self.replace:
			try:
				key.set_contents_from_file(content, replace=True)
			except Exception as e:
				raise IOError('Error during uploading file - %s' % e.message)
		else:
			if key.exists():
				raise IOError('File already exists and can\'t be replaced - %s' % name)
			else:
				try:
					key.set_contents_from_file(content, replace=False)
				except Exception as e:
					raise IOError('Error during uploading file - %s' % e.message)

		content.seek(0, 2)
		orig_size = content.tell()
		saved_size = key.size

		if saved_size == orig_size:
			key.set_acl(self.policy)
		else:
			key.delete()

			raise IOError('Error during saving file %s - saved %s of %s bytes'
			% (name, saved_size, orig_size))

		return name

	def get_available_name(self, name):
		"""
		Returns a filename that's free on the target storage system, and
		available for new content to be written to.
		Handled by Boto itself.
		"""
		return name

	def modified_time(self, name):
		return self.bucket.lookup(name).last_modified

	created_time = accessed_time = modified_time
