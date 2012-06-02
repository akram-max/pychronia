# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals

### NO import from rpgweb.common, else circular import !! ###

import sys, os, collections, logging, inspect, types, traceback, re, glob
import yaml, random, contextlib
from .counter import Counter
from datetime import datetime, timedelta

import ZODB # must be first !
import transaction
from persistent import Persistent
from persistent.dict import PersistentDict
from persistent.list import PersistentList
 
from django_zodb import database
from django.core.validators import email_re
from django.conf import settings as django_settings
from .. import default_settings as game_default_settings
  
  
class Conf(object):
    """
    Helper class which handles default game settings.
    """
    def __getattr__(self, name):
        try:
            return getattr(django_settings, name)
        except AttributeError:
            return getattr(game_default_settings, name)
    def __setattr__(self, name, value):
        raise NotImplementedError("Game conf is currently readonly")

config = Conf()
del Conf

## Python <-> ZODB types conversion and checking ##
 
python_to_zodb_types = {list: PersistentList,
                        dict: PersistentDict}

zodb_to_python_types = dict((value, key) for (key, value) in python_to_zodb_types.items())

allowed_zodb_types = (types.NoneType, int, long, float, basestring, tuple, datetime, collections.Callable, PersistentDict, PersistentList)




class Enum(set):
    """
    Takes a string of values, or a list, and exposes the corresponding enumeration.
    """
    def __init__(self, iterable=[]):
        set.__init__(self)
        self.update(iterable)

    def update(self, iterable):
        if isinstance(iterable, basestring):
            iterable = iterable.split()
        set.update(self, iterable)

    def __getattr__(self, name):
        if name in self:
            return name
        raise AttributeError(name)


class SDICT(dict):
    def __getitem__(self, name):
        try:
            return dict.__getitem__(self, name)
        except KeyError:
            logging.critical("Wrong key %s looked up in dict %r", name, self)
            return "<UNKNOWN>"
        
    ''' obsolete
    def SDICT(**kwargs):
        import collections
        # TODO - log errors when wrong lookup happens!!!
        mydict = collections.defaultdict(lambda: "<UNKNOWN>") # for safe string substitutions
        for (name, value) in kwargs.items():
            mydict[name] = value # we mimic the normal dict constructor
        return mydict
    '''
       

def monkey_patch_django_zodb_parser():
    import django_zodb.utils, django_zodb.config, django_zodb.tests.test_utils
    from django_zodb.utils import parse_uri as original_parse_uri
    
    def fixed_parse_uri(uri):
        # HACK to make it work for windows file paths !!
        if uri.startswith("file://"):
            return dict(scheme="file", path=uri[len("file://"):])
        return original_parse_uri(uri)
    
    # injection of fixed uri parser
    django_zodb.utils.parse_uri = fixed_parse_uri
    django_zodb.config.parse_uri = fixed_parse_uri
monkey_patch_django_zodb_parser()

def open_zodb_file(zodb_file):
    #print ("RETRIEVING DB FROM FILE", zodb_file)
    URI = "file://" + zodb_file.replace("\\", "/")
    # .replace(":", "|") # or "mem://"    # we have problems with URIs in win32, so replace : with |
    #print (">>>>>>", URI)
    db = database.get_database_from_uris([URI])
    return db

 
def convert_object_tree(tree, type_mapping):
    """
    Recursively transform a tree of objects (lists, dicts, instances...)
    into an equivalent structure with alternative types.
    """

    for (A, B) in type_mapping.items():
        if isinstance(tree, A):
            tree = B(tree)
            break

    if isinstance(tree, (types.NoneType, int, long, float, basestring, tuple, datetime, collections.Callable)):
        return tree # Warning - we must thus avoid infinite recursion on character sequences (aka strings)...
    elif isinstance(tree, collections.MutableSequence):
        for (index, item) in enumerate(tree):
            tree[index] = convert_object_tree(item, type_mapping)
    elif isinstance(tree, collections.MutableMapping):
        for (key, value) in tree.items():
            tree[key] = convert_object_tree(value, type_mapping)
    elif isinstance(tree, collections.MutableSet):
        for value in tree:
            tree.remove(value)
            tree.add(convert_object_tree(value, type_mapping))
    elif hasattr(tree, "__dict__"):
        for (key, value) in tree.__dict__.items():
            setattr(tree, key, convert_object_tree(value, type_mapping))
    return tree



def check_object_tree(tree, allowed_types, path):

    if not isinstance(tree, allowed_types):
        raise RuntimeError("Bad object type detected : %s - %s via path %s" % (type(tree), tree, path))


    if isinstance(tree, (int, long, basestring)):
        return

    elif isinstance(tree, collections.MutableSequence):
        for (index, item) in enumerate(tree):
            check_object_tree(item, allowed_types, path + [index])
    elif isinstance(tree, collections.MutableMapping):
        for (key, value) in tree.items():
            check_object_tree(value, allowed_types, path + [key])
    elif isinstance(tree, collections.MutableSet):
        for value in tree:
            check_object_tree(value, allowed_types, path + ["<set-item>"])
    elif hasattr(tree, "__dict__"):
        for (key, value) in tree.__dict__.items():
            check_object_tree(value, allowed_types, path + [key])



def substract_lists(available_gems, given_gems):
    available_gems = Counter(available_gems)
    given_gems = Counter(given_gems)

    if given_gems & available_gems != given_gems:
        return None # operation impossible

    gems_remaining = available_gems - given_gems
    return PersistentList(gems_remaining.elements())


def sanitize_query_dict(query_dict):
    """
    We remove terminal '[]' in request data keys and replace enforce their value to be a list
    to allow mapping of these to methods arguments (which can't contain '[]').
    
    *query_dict* must be mutable.
    """
    for key in query_dict:
        if key.endswith("[]"): # standard js/php array notation
            new_key = key[:-2]
            query_dict[new_key] = query_dict.getlist(key)
            del query_dict[key]
    print ("NE QUERY DICT", query_dict)
    return query_dict    

 
def adapt_parameters_to_func(all_parameters, func):
    """
    Strips unwanted parameters in a dict of parameters (eg. obtained via GET or POST),
    and ensures no argument is missing.

    Returns a dict of relevant parameters, or raises common signature exceptions.
    """
    

    (args, varargs, keywords, defaults) = inspect.getargspec(func)
    print("########", func, all_parameters, args)
    
    if keywords is not None:
        relevant_args = all_parameters # exceeding args will be handled properly
    else:
        relevant_args = dict((key, value) for (key, value) in all_parameters.items() if key in args)

    try:
        #print("#<<<<<<<", func, relevant_args)
        inspect.getcallargs(func, **relevant_args)
    except (TypeError, ValueError), e:
        raise

    return relevant_args


## Tools for database sanity checks ##



def check_no_duplicates(value):
    assert len(set(value)) == len(value), value
    return True
    
def check_is_range_or_num(value):
    if isinstance(value, (int, long, float)):
        pass # nothing to check
    else:
        assert isinstance(value, (tuple, PersistentList)), value
        assert len(value) == 2, value
        assert isinstance(value[0], (int, long, float)), value
        assert isinstance(value[1], (int, long, float)), value
        assert value[0] <= value[1], value
    return True

def check_is_lazy_object(value):
    assert value.__class__.__name__ == "__proxy__", type(value)
    return True

def check_is_string(value):
    assert isinstance(value, basestring) and value, value
    return True

def check_is_int(value):
    assert isinstance(value, (int, long)), value
    return True

def check_is_email(email):
    assert email_re.match(email)
    return True

def check_is_slug(value):
    assert isinstance(value, basestring), repr(value)
    assert " " not in value, repr(value)
    assert "\n" not in value, repr(value)
    return True

def check_is_bool(value):
    assert isinstance(value, bool), value
    return True

def check_is_list(value):
    assert isinstance(value, collections.Sequence), value
    return True

def check_is_dict(value):
    assert isinstance(value, collections.Mapping), value
    return True

def check_num_keys(value, num):
    assert len(value.keys()) == num, (value, num)
    return True

def check_is_positive_int(value, non_zero=True):
    assert isinstance(value, (int, long))
    assert value >= 0
    if non_zero:
        assert value != 0
    return True

def check_is_restructuredtext(value):
    from django.contrib.markup.templatetags.markup import restructuredtext
    assert restructuredtext(value)
    return True

def check_is_game_file(*paths_elements):
    assert os.path.isfile(os.path.join(config.GAME_FILES_ROOT, *paths_elements))
    return True

def is_email(email):
    return email_re.match(email)

def assert_sets_equal(set1, set2):

    # in case they are lists
    set1 = set(set1)
    set2 = set(set2)

    exceeding_keys1 = set1 - set2
    if exceeding_keys1:
        raise ValueError("Exceeding keys in first set: %r" % repr(exceeding_keys1))

    exceeding_keys2 = set2 - set1
    if exceeding_keys2:
        raise ValueError("Exceeding keys in second set: %r" % repr(exceeding_keys2))

    assert set1 == set2 # else major coding error
    return True


def validate_value(value, validator):

    if issubclass(type(validator), types.TypeType) or isinstance(validator, (list, tuple)): # should be a list of types
        assert isinstance(value, validator)

    elif isinstance(validator, collections.Callable):
        res = validator(value)
        assert res, (repr(res), repr(validator))

    else:
        raise RuntimeError("Invalid configuration validator %r for value %r" % (validator, value))


def check_dictionary_with_template(my_dict, template, strict=False):
    # checks that the keys and value types of a dictionary matches that of a template

    if strict:
        assert_sets_equal(my_dict.keys(), template.keys())
    else:
        assert set(template.keys()) <= set(my_dict.keys())

    for key in template.keys():
        validate_value(my_dict[key], template[key])


def load_yaml_file(yaml_file):
    with open(yaml_file, "U") as f:
        raw_data = f.read()

    for (lineno, linestr) in enumerate(raw_data.split(b"\n"), start=1):
        if b"\t" in linestr:
            raise ValueError("Forbidden tabulation found at line %d in yaml file %s : '%r'!" % (lineno, yaml_file, linestr))
    
    data = yaml.load(raw_data)
    return data


YAML_EXTENSIONS = ["*.yaml", "*.yml"]
def load_yaml_fixture(yaml_fixture):
    """
    Can load a single yaml file, or a directory containing y[a]ml files.
    Each file must only contain a single yaml document.
    """
    
    if not os.path.exists(yaml_fixture):
        raise ValueError(yaml_fixture)
    if os.path.isfile(yaml_fixture):
        data = load_yaml_file(yaml_fixture)
    else:
        assert os.path.isdir(yaml_fixture)
        data = {}
        yaml_files = [path for pattern in YAML_EXTENSIONS
                      for path in glob.glob(os.path.join(yaml_fixture, pattern))]
        del yaml_fixture # security
        for yaml_file in yaml_files:
            part = load_yaml_file(yaml_file)
            if not isinstance(part, dict) or (set(part.keys()) & set(data.keys())):
                raise ValueError("Improper or colliding content in %s" % yaml_file)
            for key, value in part.items():
                data.update(part)
    return data
    

    





### Date operations ###

def utc_to_local(utc_time):
    timedelta = datetime.now() - datetime.utcnow()
    return utc_time + timedelta



def compute_remote_datetime(delay_mn):
    # delay can be a number or a range (of type int or float)
    # we always work in UTC

    new_time = datetime.utcnow()

    if delay_mn:
        if not isinstance(delay_mn, (int, long, float)):
            delay_s_min = int(60 * delay_mn[0])
            delay_s_max = int(60 * delay_mn[1])
            assert delay_s_min <= delay_s_max, "delay min must be < delay max"

            delay_s = random.randint(delay_s_min, delay_s_max) # time range in seconds


        else:
            delay_s = 60 * delay_mn  # no need to coerce to integer

        #print "DELAY ADDED : %s s" % delay_s

        new_time += timedelta(seconds=delay_s)

    return new_time


def is_past_datetime(dt):
    # WARNING - to compute delays, we always work in UTC TIME
    return (dt <= datetime.utcnow())





@contextlib.contextmanager
def exception_swallower():
    """
    When called, this function returns a context manager which
    catches and logs all exceptions raised inside its
    block of code (useful for rarely crossed try...except clauses,
    to swallow unexpected name or string formatting errors).
    """

    try:
        yield
    except Exception, e:
        try:
            logging.critical(_("Unexpected exception occurred in exception swallower context : %r !"), e, exc_info=True)
        except Exception:
            print >> sys.stderr, _("Exception Swallower logging is broken !!!")

        if __debug__:
            raise RuntimeError(_("Unexpected exception occurred in exception swallower context : %r !") % e)



def make_bi_usage_decorator(decorator):
    """
    Transforms a decorator taking default arguments, into a decorator that can both
    be applied directly to a callable, or first parameterized with keyword arguments and then applied.
    
    i.e:
    
        @decorator(a=3, b=5)
        def myfunc...
        
        OR
        
        @decorator # default arguments are applied
        def myfunc...
        
    The trouble is that static code analysis loses track of decorator signature...
    """
    def bidecorator(object=None, **kwargs):
        factory = lambda x: decorator(x, **kwargs)
        if object: 
            return factory(object)
        return factory
    return bidecorator



class TechnicalEventsMixin(object):
    """
    This private registry keeps track of miscellaneous events sent throughout the datamanager system.
    This feature should solely be used for debugging purpose, with function calls protected by
    ``if __debug__:`` statements for optimization.
    To prevent naming collisions, an error is raised if events with the same name
    are sent from different locations.
    """

    def __init__(self, *args, **kwargs):
        super(TechnicalEventsMixin, self).__init__(*args, **kwargs)
        self._event_registry = {} # stores, for each event name, a (calling_frame, count) tuple


    def notify_event(self, event_name):
        """
        Records the sending of event *event_name*.
        """
        calling_frame = traceback.extract_stack(limit=2)[0] # we capture the frame which called notify_event()
        if not self._event_registry.has_key(event_name):
            self._event_registry[event_name] = (calling_frame, 1)
        else:
            (old_calling_frame, cur_count) = self._event_registry[event_name]
            if calling_frame != old_calling_frame:
                raise RuntimeError("Duplicated event name %s found for locations '%s' and '%s'" % (
                                    event_name, old_calling_frame, calling_frame))
            self._event_registry[event_name] = (calling_frame, cur_count + 1)


    def get_event_count(self, event_name):
        """
        Returns the number of times the event *event_name* has been sent since the last
        clearing of its statistics.
        """
        if not self._event_registry.has_key(event_name):
            return 0
        else:
            return self._event_registry[event_name][1]


    def clear_event_stats(self, event_name):
        """
        Resets to 0 the counter of the event *event_name*.
        """
        del self._event_registry[event_name]


    def clear_all_event_stats(self):
        """
        Resets entirely the event system, eg. at the beginning of a test sequence.
        """
        self._event_registry = {}






## conversions between variable naming conventions ##

def to_snake_case(text):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', text)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()

def to_pascal_case(text):
    if "_" in text:
        callback = lambda pat: pat.group(1).lower() + pat.group(2).upper()
        text = re.sub("(\w)_(\w)", callback, text)
        if text[0].islower():
            text = text[0].upper() + text[1:]
        return text
    return text[0].upper() + text[1:]

def to_camel_case(text):
    text = to_pascal_case(text)
    return text[0].lower() + text[1:]



