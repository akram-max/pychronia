# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals


from pychronia_game.common import *
from django.contrib import messages



class GameUser(object):

    def __init__(self, datamanager, username=None,
                 impersonation_target=None, impersonation_writability=False,
                 is_superuser=False):
        """
        Builds a user object, storing notifications for the current HTTP request,
        and exposing shortcuts to useful data.
        
        Existence of provided logins is checked, not the permission to use them 
        (which must be done at upper levels).
        
        If is_superuser (django notion, different from is_master), user can impersonate anyone, 
        yet keep his real_username as anonymous.
        """
        assert impersonation_writability in (None, True, False)
        impersonation_writability = bool(impersonation_writability) # we don't care about genesis details here, None => False
        # data normalization #
        _game_anonymous_login = datamanager.anonymous_login
        _available_logins = datamanager.get_available_logins()

        if username is None:
            username = _game_anonymous_login # better than None, to display in templates

        if username not in _available_logins:
            raise AbnormalUsageError(_("Username %s is unknown") % username)
        if impersonation_target and impersonation_target not in _available_logins:
            raise AbnormalUsageError(_("Impersonation target %s is unknown") % impersonation_target)

        assert not impersonation_target or is_superuser or datamanager.can_impersonate(username, impersonation_target)
        assert not (is_superuser and username != _game_anonymous_login) # game authentication "hides" the superuser status
        assert is_superuser or datamanager.is_master(username) or not impersonation_target or not impersonation_writability # atm only special user can take full control of other user

        self.is_superuser = is_superuser # REAL state of user, whatever impersonation is happening
        self._real_username = username
        self.is_impersonation = bool(impersonation_target)
        self.impersonation_target = impersonation_target
        self.impersonation_writability = impersonation_writability # saved even we're not currently impersonating

        self.has_write_access = bool(impersonation_writability) if impersonation_target else True # normal logged-in user always HAS write access ATM

        _effective_username = (impersonation_target if impersonation_target else username)
        assert _effective_username in _available_logins # redundant but yah...
        del username, impersonation_target, impersonation_writability, _game_anonymous_login # security

        self.is_master = datamanager.is_master(_effective_username)
        self.is_character = datamanager.is_character(_effective_username)
        self.is_anonymous = datamanager.is_anonymous(_effective_username)
        self.is_authenticated = not self.is_anonymous
        self._effective_username = _effective_username

        assert len([item for item in (self.is_master, self.is_character, self.is_anonymous) if item]) == 1
        assert self.is_superuser or datamanager.is_master(self._real_username) or not self.impersonation_writability # normal players can NEVER impersonate with write access

        self._datamanager = weakref.ref(datamanager)



    @property
    def datamanager(self):
        return self._datamanager()

    @property
    def real_username(self):
        return self._real_username

    @property
    def username(self):
        """
        Returns *effective* user name!!
        """
        return self._effective_username

    def character_properties(self):
        """
        Only for normal players.
        """
        assert self.is_character, [self._effective_username]
        return self._datamanager().get_character_properties(self._effective_username)

    def has_permission(self, permission):
        return self._datamanager().has_permission(username=self.username, permission=permission)



    ## Persistent user messages, using django.contrib.messages ##

    def _check_request_available(self):
        if not self.datamanager.request:
            self.datamanager.logger.critical("Unexisting request object looked up by GameUser", exc_info=True)
            return False
        return True

    def add_message(self, message):
        if self._check_request_available():
            messages.success(self.datamanager.request, message) # shared between all game instances...

    def add_warning(self, message):
        if self._check_request_available():
            messages.warning(self.datamanager.request, message) # shared between all game instances...

    def add_error(self, error):
        if self._check_request_available():
            messages.error(self.datamanager.request, error) # shared between all game instances...

    def get_notifications(self):
        """
        Messages will only be deleted after being iterated upon.
        """
        if self._check_request_available():
            return messages.get_messages(self.datamanager.request)
        else:
            return []

    def has_notifications(self):
        if self._check_request_available():
            return bool(len(messages.get_messages(self.datamanager.request)))
        return False

    def discard_notifications(self):
        from django.contrib.messages.storage import default_storage
        if self._check_request_available():
            self.datamanager.request._messages = default_storage(self.datamanager.request) # big hack





''' USELESS
    def _dm_call_forwarder(self, func_name, *args, **kwargs):
        """
        Forwards call to the select function of the attached datamanager, 
        transferring given arguments.
        """
        target = getattr(self._datamanager(), func_name)
        return target(*args, **kwargs)

    def __getattr__(self, name):
        """
        Helper to call methods of the datamanager, 
        forcing *username* to the currently selected username.
        
        Will fail if target method doesn't expect a username argument, 
        or if current user isn't of a proper type.
        """
        obj = getattr(self._datamanager(), name)
        
        if inspect.isroutine(obj):
            return functools.partial(self._dm_call_forwarder,
                                     func_name=name,
                                     username=self._effective_username)
        else:
            return obj
    '''