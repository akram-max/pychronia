# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals

from rpgweb.common import *


from .datamanager_administrator import GameDataManager
from .datamanager_tools import readonly_method, transaction_watcher
from .abstract_game_view import GameViewMetaclass, AbstractGameView
from .action_middlewares import ACTION_MIDDLEWARES



class AbilityMetaclass(GameViewMetaclass, type):
    """
    Metaclass automatically registering the new ability (which is also a view) in a global registry.
    """
    def __init__(NewClass, name, bases, new_dict):

        super(AbilityMetaclass, NewClass).__init__(name, bases, new_dict)

        if not NewClass.__name__.startswith("Abstract"):

            if __debug__:
                pass
                #RESERVED_NAMES = AbstractAbility.__dict__.keys()
                ##assert utilities.check_is_lazy_object(NewClass.TITLE) # NO - unused atm !! delayed translation

            GameDataManager.register_ability(NewClass)




# just because we can't dynamically assign a tuple of bases, in a normal "class" definition
AbstractAbilityBases = tuple(reversed(ACTION_MIDDLEWARES)) + (AbstractGameView,)
AbstractAbilityBasesAdapter = AbilityMetaclass(str('AbstractAbilityBasesAdapter'), AbstractAbilityBases, {})



"""
print (">>>>>>>>>", AbstractAbilityBases)

for _base in AbstractAbilityBases:
    print (_base, type(_base))
    assert issubclass(AbilityMetaclass, type(_base))
"""


class AbstractAbility(AbstractAbilityBasesAdapter):

    ### Uses AbstractAbilityBases metaclass ###
    ### Inherites from both action middlewares and AbstractGameView ###

    # NOT ATM - TITLE = None # menu title, use lazy gettext when setting

    def __init__(self, request, *args, **kwargs):
        super(AbstractAbility, self,).__init__(request, *args, **kwargs)
        self._ability_data = weakref.ref(self.datamanager.get_ability_data(self.NAME))
        self.logger = self.datamanager.logger # local cache


    @property
    def datamanager(self):
        return self # TRICK - abilities behaves as extensions of the datamanager!!


    @transaction_watcher(ensure_data_ok=True, ensure_game_started=False) # needed, because in ability, we're partly INSIDE the datamanager
    def _process_standard_request(self, request, *args, **kwargs):
        # Access checks have already been done here, so we may initialize lazy data
        self._perform_lazy_initializations()
        return super(AbstractAbility, self)._process_standard_request(request, *args, **kwargs)


    def __getattr__(self, name):
        assert not name.startswith("_") # if we arrive here, it's probably a typo in an attribute fetching
        try:
            value = getattr(self._inner_datamanager, name)
        except AttributeError:
            raise AttributeError("Neither ability nor datamanager has attribute '%s'" % name)
        return value


    @property
    def ability_data(self):
        return self._ability_data() # could be None


    @property
    def settings(self):
        return self._ability_data()["settings"]


    @property
    def private_data(self):
        """
        Also works for anonymous access (anonymous users share their data,
        whereas authenticated ones have their one data slot).
        """
        private_key = self._get_private_key()
        return self._ability_data()["data"][private_key]


    def _get_private_key(self):
        return self._inner_datamanager.user.username # can be "anonymous", a character or a superuser login!


    @property
    def all_private_data(self):
        return self._ability_data()["data"]


    def get_ability_parameter(self, name):
        return self.settings[name]


    '''
    @classmethod
    def get_menu_title(cls):
        return cls.TITLE
    '''

    @readonly_method
    def get_ability_summary(self):
        # FIXME - how does it work actually ?
        return self._get_ability_summary()


    def _get_ability_summary(self):
        """
        Summary for super user ?
        """
        raise NotImplementedError




    @classmethod
    def setup_main_ability_data(cls, ability_data):
        # no transaction handling here - it's all up to the caller of that classmethod
        settings = ability_data.setdefault("settings", PersistentDict())
        ability_data.setdefault("data", PersistentDict())
        cls._setup_ability_settings(settings=settings) # FIRST
        cls._setup_action_middleware_settings(settings=settings) # SECOND


    @classmethod
    def _setup_ability_settings(cls, settings):
        pass # to be overridden


    @transaction_watcher(ensure_game_started=False) # authorized anytime
    def _perform_lazy_initializations(self):
        private_key = self._get_private_key()
        #print ("@@@@@@@@@@", self.ability_data)
        if not self.ability_data["data"].has_key(private_key):
            self.logger.warning("Setting up private data %s", private_key)
            private_data = self.ability_data["data"].setdefault(private_key, PersistentDict())
            self._setup_private_ability_data(private_data=private_data) # FIRST
            self._setup_private_action_middleware_data(private_data=private_data) # SECOND



    def _setup_private_ability_data(self, private_data):
        """
        Not called in the case of game-level abilities
        """
        raise NotImplementedError("_setup_private_ability_data") # to be overridden


    @readonly_method
    def check_data_sanity(self, strict=False):

        # self.logger.debug("Checking data sanity")

        assert isinstance(self.ability_data["settings"], collections.Mapping), self.ability_data["settings"]
        assert isinstance(self.ability_data["data"], collections.Mapping), self.ability_data["data"]

        if strict:
            available_logins = self._inner_datamanager.get_available_logins()
            for name, value in self.ability_data["data"].items():
                assert name in available_logins
                assert isinstance(value, collections.Mapping)

        self._check_action_middleware_data_sanity(strict=strict)
        self._check_data_sanity(strict=strict)


    def _check_data_sanity(self, strict=False):
        raise NotImplementedError("_check_data_sanity") # to be overridden



    '''
    def _instantiate_form(self,
                          new_form_name, 
                          hide_on_success=False,
                          previous_form_data=None, 
                          initial_data=None,
                          form_initializer=None):
        form_initializer = form_initializer if form_initializer else self # the ability behaves as an extended datamanager
        return super(AbstractAbility, self)._instantiate_form(new_form_name=new_form_name, 
                                                              hide_on_success=hide_on_success,
                                                              previous_form_data=previous_form_data,
                                                              initial_data=initial_data,
                                                              form_initializer=form_initializer) 
       '''







'''
    def _check_permissions(self):
        ###USELESS
        """
        This method should be called at django view level only, not from another ability
        method (unittests don't have to care about permissions).
        """
        user = self.datamanager.user
        
        if self.ACCESS == "master":
            if not user.is_master:
                raise PermissionError(_("Ability reserved to administrators"))
        elif self.ACCESS == "player":
            if not user.is_character:
                raise PermissionError(_("Ability reserved to standard users"))
            if not user.has_permission(self.NAME):
                # todo - what permission tokens do we use actually for abilities ??
                raise PermissionError(_("Ability reserved to privileged users"))
        elif self.ACCESS == "authenticated":
            if not user.is_authenticated:
                raise PermissionError(_("Ability reserved to registered users"))
        else:
            assert self.ACCESS == "anonymous"


    def _____get_action_contexts(self): #TODO REMOVE
        private_key = self._get_private_key()
        if private_key:
            private_data = self.ability_data[private_key]
        else:
            private_data = None
        return (self.ability_data["settings"], private_data)

 
    def __init__(self, ability_name, max_items, items_available=0):
        self.__ability_name = ability_name
        self.__record = PersistentDict(
                                         items_consumed=0,
                                         items_available=items_available,
                                         max_items=max_items,
                                         item_price=item_price
                                      )

    def _ability_retrieve_record(ability_name):
        assert ability_name == self.__ability_name
        return self.__record

    ###################################################################



    def ability_get_team_value(ability_name, field):
        record = self._ability_retrieve_record(ability_name)
        return record[field]


    def ability_check_record_coherency(self, ability_name):
        record = self._ability_retrieve_record(ability_name)
        for (key, value) in record.items():
            assert isinstance(value, (int, long)), record
            assert value >= 0
        assert record["items_consumed"] + record["items_available"] <= record["max_items"]


    def ability_consume(self, ability_name, num_consumed=1):
        record = self._ability_retrieve_record(ability_name)

        if num_consumed >= record["items_available"]:
            raise NormalUsageError(_("Not enough '%s' items to consume"))

        record["items_available"] -= num_consumed
        record["items_consumed"] += num_consumed


    def ability_buy(self, ability_name, num_bought=1):
        record = self._ability_retrieve_record(ability_name)

        if record["items_consumed"] + record["items_available"] + num_bought > record["max_items"]:
            raise NormalUsageError(_("Impossible to get more than '%s' items altogether"))

        record["items_available"] += num_bought


    def ability_raise_limit(self, ability_name, num_more=1):

        record["max_items"] += num_more
'''

'''
    Abilities may be bought, used, and their maximum number changed
    according to game events.

    Ability record fields:
        items_consumed     # how many items are used and over (eg. scan operations completed)
        items_available     # how many items are ready for use, in a persistent (eg. listening slots) or temporary (eg. teleportations) way
        max_items     # limit value for (items_used+items_available)
        item_price     # how much it costs to have one more available item
        payment_types # tuple of values from ["gems", "money"]
'''