# Copyright (c) 2014 Rackspace US, Inc
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
import os
import stat
import uuid

from oslo_config import cfg
from oslo_log import log as logging

from octavia.certificates.common import local as local_common
from octavia.certificates.manager import cert_mgr
from octavia.common import exceptions
from octavia.common.tls_utils import cert_parser

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class LocalCertManager(cert_mgr.CertManager):
    """Cert Manager Interface that stores data locally."""

    @staticmethod
    def store_cert(context, certificate, private_key, intermediates=None,
                   private_key_passphrase=None, **kwargs):
        """Stores (i.e., registers) a cert with the cert manager.

        This method stores the specified cert to the filesystem and returns
        a UUID that can be used to retrieve it.

        :param context: Ignored in this implementation
        :param certificate: PEM encoded TLS certificate
        :param private_key: private key for the supplied certificate
        :param intermediates: ordered and concatenated intermediate certs
        :param private_key_passphrase: optional passphrase for the supplied key

        :returns: the UUID of the stored cert
        :raises CertificateStorageException: if certificate storage fails
        """
        cert_ref = str(uuid.uuid4())
        filename_base = os.path.join(CONF.certificates.storage_path, cert_ref)
        if isinstance(certificate, bytes):
            certificate = certificate.decode('utf-8')
        if isinstance(private_key, bytes):
            private_key = private_key.decode('utf-8')

        LOG.info("Storing certificate data on the local filesystem.")
        try:
            filename_certificate = f"{filename_base}.crt"
            flags = os.O_WRONLY | os.O_CREAT
            mode = stat.S_IRUSR | stat.S_IWUSR  # mode 0600
            with os.fdopen(os.open(
                    filename_certificate, flags, mode), 'w') as cert_file:
                cert_file.write(certificate)

            filename_private_key = f"{filename_base}.key"
            with os.fdopen(os.open(
                    filename_private_key, flags, mode), 'w') as key_file:
                key_file.write(private_key)

            if intermediates:
                filename_intermediates = f"{filename_base}.int"
                if isinstance(intermediates, bytes):
                    intermediates = intermediates.decode('utf-8')
                with os.fdopen(os.open(
                        filename_intermediates, flags, mode), 'w') as int_file:
                    int_file.write(intermediates)

            if private_key_passphrase:
                filename_pkp = f"{filename_base}.pass"
                if isinstance(private_key_passphrase, bytes):
                    private_key_passphrase = private_key_passphrase.decode(
                        'utf-8')
                with os.fdopen(os.open(
                        filename_pkp, flags, mode), 'w') as pass_file:
                    pass_file.write(private_key_passphrase)
        except OSError as ioe:
            LOG.error("Failed to store certificate.")
            raise exceptions.CertificateStorageException(message=ioe.message)

        return cert_ref

    @staticmethod
    def get_cert(context, cert_ref, **kwargs):
        """Retrieves the specified cert.

        :param context: Ignored in this implementation
        :param cert_ref: the UUID of the cert to retrieve

        :return: octavia.certificates.common.Cert representation of the
                 certificate data
        :raises CertificateStorageException: if certificate retrieval fails
        """
        LOG.info("Loading certificate %s from the local filesystem.", cert_ref)

        filename_base = os.path.join(CONF.certificates.storage_path, cert_ref)

        filename_certificate = f"{filename_base}.crt"
        filename_private_key = f"{filename_base}.key"
        filename_intermediates = f"{filename_base}.int"
        filename_pkp = f"{filename_base}.pass"

        cert_data = {}

        flags = os.O_RDONLY
        try:
            with os.fdopen(os.open(filename_certificate, flags)) as cert_file:
                cert_data['certificate'] = cert_file.read()
        except OSError as e:
            LOG.error("Failed to read certificate for %s.", cert_ref)
            raise exceptions.CertificateStorageException(
                msg="Certificate could not be read.") from e
        try:
            with os.fdopen(os.open(filename_private_key, flags)) as key_file:
                cert_data['private_key'] = key_file.read()
        except OSError as e:
            LOG.error("Failed to read private key for %s", cert_ref)
            raise exceptions.CertificateStorageException(
                msg="Private Key could not be read.") from e

        try:
            with os.fdopen(os.open(filename_intermediates, flags)) as int_file:
                cert_data['intermediates'] = int_file.read()
            cert_data['intermediates'] = list(
                cert_parser.get_intermediates_pems(cert_data['intermediates']))
        except OSError:
            pass

        try:
            with os.fdopen(os.open(filename_pkp, flags)) as pass_file:
                cert_data['private_key_passphrase'] = pass_file.read()
        except OSError:
            pass

        return local_common.LocalCert(**cert_data)

    @staticmethod
    def delete_cert(context, cert_ref, **kwargs):
        """Deletes the specified cert.

        :param context: Ignored in this implementation
        :param cert_ref: the UUID of the cert to delete

        :raises CertificateStorageException: if certificate deletion fails
        """
        LOG.info("Deleting certificate %s from the local filesystem.",
                 cert_ref)

        filename_base = os.path.join(CONF.certificates.storage_path, cert_ref)

        filename_certificate = f"{filename_base}.crt"
        filename_private_key = f"{filename_base}.key"
        filename_intermediates = f"{filename_base}.int"
        filename_pkp = f"{filename_base}.pass"

        try:
            os.remove(filename_certificate)
            os.remove(filename_private_key)
            os.remove(filename_intermediates)
            os.remove(filename_pkp)
        except OSError as ioe:
            LOG.error("Failed to delete certificate %s", cert_ref)
            raise exceptions.CertificateStorageException(message=ioe.message)

    def set_acls(self, context, cert_ref):
        # There is no security on this store, because it's really dumb
        pass

    def unset_acls(self, context, cert_ref):
        # There is no security on this store, because it's really dumb
        pass

    @staticmethod
    def get_secret(context, secret_ref):
        """Retrieves a secret payload by reference.

        :param context: Ignored in this implementation
        :param secret_ref: The secret reference ID

        :return: The secret payload
        :raises CertificateStorageException: if secret retrieval fails
        """
        LOG.info("Loading secret %s from the local filesystem.", secret_ref)

        filename_base = os.path.join(CONF.certificates.storage_path,
                                     secret_ref)

        filename_secret = f"{filename_base}.crt"

        secret_data = None

        flags = os.O_RDONLY
        try:
            with os.fdopen(os.open(filename_secret, flags)) as secret_file:
                secret_data = secret_file.read()
        except OSError as e:
            LOG.error("Failed to read secret for %s.", secret_ref)
            raise exceptions.CertificateRetrievalException(
                ref=secret_ref) from e

        return secret_data
