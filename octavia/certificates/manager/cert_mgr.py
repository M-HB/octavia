# Copyright (c) 2013 The Johns Hopkins University/Applied Physics Laboratory
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

"""
Certificate manager API
"""
import abc


class CertManager(metaclass=abc.ABCMeta):
    """Base Cert Manager Interface

    A Cert Manager is responsible for managing certificates for TLS.
    """

    @abc.abstractmethod
    def store_cert(self, context, certificate, private_key, intermediates=None,
                   private_key_passphrase=None, expiration=None, name=None):
        """Stores (i.e., registers) a cert with the cert manager.

        This method stores the specified cert and returns its UUID that
        identifies it within the cert manager.
        If storage of the certificate data fails, a CertificateStorageException
        should be raised.
        """

    @abc.abstractmethod
    def get_cert(self, context, cert_ref, resource_ref=None, check_only=False,
                 service_name=None):
        """Retrieves the specified cert.

        If check_only is True, don't perform any sort of registration.
        If the specified cert does not exist, a CertificateStorageException
        should be raised.
        """

    @abc.abstractmethod
    def delete_cert(self, context, cert_ref, resource_ref, service_name=None):
        """Deletes the specified cert.

        If the specified cert does not exist, a CertificateStorageException
        should be raised.
        """

    @abc.abstractmethod
    def set_acls(self, context, cert_ref):
        """Adds ACLs so Octavia can access the cert objects.

        If the specified cert does not exist or the addition of ACLs fails for
        any reason, a CertificateStorageException should be raised.
        """

    @abc.abstractmethod
    def unset_acls(self, context, cert_ref):
        """Remove ACLs so Octavia can access the cert objects.

        If the specified cert does not exist or the removal of ACLs fails for
        any reason, a CertificateStorageException should be raised.
        """

    @abc.abstractmethod
    def get_secret(self, context, secret_ref):
        """Retrieves a secret payload by reference.

        If the specified secret does not exist, a CertificateStorageException
        should be raised.
        """
