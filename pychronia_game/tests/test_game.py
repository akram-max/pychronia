# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals

import random
from textwrap import dedent
import tempfile
import shutil

from ._test_tools import *
from ._dummy_abilities import *

import fileservers
from django.utils import timezone
from pychronia_game.datamanager.abstract_ability import AbstractAbility
from pychronia_game.datamanager.action_middlewares import CostlyActionMiddleware, \
    CountLimitedActionMiddleware, TimeLimitedActionMiddleware
from pychronia_game.common import _undefined, config, AbnormalUsageError, reverse, \
    UsageError, checked_game_file_path
from pychronia_game.templatetags.helpers import _generate_encyclopedia_links, \
    advanced_restructuredtext, _generate_messaging_links, _generate_site_links, \
    _enriched_text, _generate_game_file_links
from pychronia_game import views, utilities
from pychronia_game.utilities import autolinker
from django.test.client import RequestFactory
import pprint
from pychronia_game.datamanager.datamanager_administrator import retrieve_game_instance, \
    _get_zodb_connection, GameDataManager, get_all_instances_metadata, \
    delete_game_instance, check_zodb_structure
from pychronia_game.tests._test_tools import temp_datamanager
import inspect
from django.forms.fields import Field
from django.core.urlresolvers import resolve
from pychronia_game.views import friendship_management
from pychronia_game.views.abilities import house_locking, \
    wiretapping_management, runic_translation
from django.contrib.auth.models import User
from pychronia_game.authentication import clear_all_sessions
from pychronia_game.utilities.mediaplayers import generate_image_viewer
from django.utils.functional import Promise








class TestUtilities(BaseGameTestCase):
    '''
    def __call__(self, *args, **kwds):
        return unittest.TestCase.run(self, *args, **kwds) # we bypass test setups from django's TestCase, to use py.test instead
        '''
    def test_restructuredtext_handling(self):
        from docutils.utils import SystemMessage

        restructuredtext = advanced_restructuredtext # we use our own version

        assert restructuredtext("""aaaa*aaa""") # star is ignored

        # outputs errors on stderr, but doesn't break
        restructuredtext("""aaaaaaa*zezez
                              mytitle :xyz:`qqq`
                            ===
                        """) # too short underline

        assert "title1" in restructuredtext("""title1\n=======\n\naaa""") # thx to our conf, title1 stays in html fragment

        #print("\n-_-\n", file=sys.stderr)

        html = restructuredtext(dedent("""
                    title1
                    -------
                    
                    aaa   
                      
                    title2
                    -------
                    
                    bbbbb
                    
                    .. embed_audio:: http://mydomain.com/myfile<ABC
                    
                    .. embed_video:: https://hi.com/a&b.flv
                        :width: 219px
                        :height: 121px
                        :image: /a<kl.jpg
               
                    .. embed_image:: https://hisss.com/a&b.jpg
                        :alias: default
                          
                    """))

        assert "title1" in html and "title2" in html

        for mystr in ("<object", "audioplayer", "http%3A%2F%2Fmydomain.com%2Fmyfile%3CABC"): # IMPORTANT - url-escaping of file url
            assert mystr in html

        for mystr in ("<object", "mediaplayer", "https://hi.com/a&amp;b.flv"): # AT LEAST html-escaped, but urlescaping could be necessary for some media types
            assert mystr in html

        for mystr in ("<img class=\"imageviewer\"", "https://hisss.com/a&amp;b.jpg", "450px"): # fallback to default width/height since image url is buggy (so easy-thumbnails fails)
            assert mystr in html




        # IMPORTANT - security measures #

        html = restructuredtext(dedent("""
        
                    .. include:: manage.py
                    
                    """))
        assert "System Message" in html and "directive disabled" in html
        assert "django" not in html

        html = restructuredtext(dedent("""
        
                    .. raw:: python
                        :file: manage.py
                    
                    """))
        assert "System Message" in html and "directive disabled" in html
        assert "django" not in html


        html = restructuredtext(dedent("""
        
                    .. raw:: html
                    
                        <script></script>
                        
                    
                    """))
        assert "System Message" in html and "directive disabled" in html
        assert "<script" not in html



        # now our settings overrides, do they work ?
        buggy_rst = dedent("""
        
                    mytitle
                    ========
                    
                    bad *text `here
                    
                    :xyzizjzb:`qqq`
                    
                    """)


        html = restructuredtext(buggy_rst,
                    initial_header_level=2,
                    report_level=1)
        ## print (">>>>>>>>>>", html)
        assert "<h2" in html
        assert "System Message" in html # specific error divs
        assert 'class="problematic"' in html # spans around faulty strings


        html = restructuredtext(buggy_rst,
                    initial_header_level=2,
                    report_level=4)
        ## print (">>>>>>>>>>", html)
        assert "<h2" in html
        assert "System Message" not in html # no additional error divs
        assert 'class="problematic"' in html # spans remain though




    def test_sphinx_publisher_settings(self) :
        from django.utils.encoding import smart_str, force_unicode
        from docutils.core import publish_parts
        docutils_settings = {"initial_header_level": 3,
                             "doctitle_xform": False,
                             "sectsubtitle_xform": False}
        parts = publish_parts(source=smart_str("""title\n=======\n\naaa\n"""), # lone title would become document title by default - we prevent it
                              writer_name="html4css1", settings_overrides=docutils_settings)
        assert parts["fragment"] == '<div class="section" id="title">\n<h3>title</h3>\n<p>aaa</p>\n</div>\n'
        # pprint.pprint(parts)


    def test_html_autolinker(self):

        regex = autolinker.join_regular_expressions_as_disjunction(("[123]", "(k*H?)"), as_words=False)
        assert regex == r"(?:[123])|(?:(k*H?))"
        assert re.compile(regex).match("2joll")

        regex = autolinker.join_regular_expressions_as_disjunction(("[123]", "(k*H)"), as_words=True)
        assert regex == r"(?:\b[123]\b)|(?:\b(k*H)\b)"
        assert re.compile(regex).match("kkH")


        input0 = '''one<a>ones</a>'''
        res = autolinker.generate_links(input0, "ones?", lambda x: dict(href="TARGET_" + x.group(0), title="mytitle"))
        assert res == '''<a href="TARGET_one" title="mytitle">one</a><a>ones</a>'''


        input = dedent('''
        <html>
        <head><title>Page title one</title></head>
        <body>
        <div>Hi</div>
        <p id="firstpara" class="one red" align="center">This is one paragraph <b>ones</b>.</a>
        <a href="http://aaa">This is one paragraph <b>one</b>.</a>
        </html>''')

        res = autolinker.generate_links(input, "ones?", lambda x: dict(href="TARGET_" + x.group(0), title="mytitle"))

        assert res == dedent('''
        <html>
        <head><title>Page title one</title></head>
        <body>
        <div>Hi</div>
        <p align="center" class="one red" id="firstpara">This is <a href="TARGET_one" title="mytitle">one</a> paragraph <b><a href="TARGET_ones" title="mytitle">ones</a></b>.
        <a href="http://aaa">This is one paragraph <b>one</b>.</a>
        </p></body></html>''')



    def test_generate_image_viewer(self):

        self._reset_django_db()

        code = generate_image_viewer("http://otherdomain/myimage.jpg")
        assert 'src="http://otherdomain/myimage.jpg"' in code # untouched

        local_img_url = game_file_url("unexisting/img.jpg")
        code = generate_image_viewer(local_img_url, preset=random.choice(("default", "badalias")))
        assert "unexisting/img.jpg" in code

        real_img = "personal_files/master/1236637123369.jpg"
        utilities.check_is_game_file(real_img)
        local_img_url = game_file_url(real_img)
        code = generate_image_viewer(local_img_url, preset=random.choice(("default", "badalias")))
        assert real_img in code # as target only
        assert "thumbs/" in code


    def test_type_conversions(self):

        # test 1 #

        class dummy(object):
            def __init__(self):
                self.attr1 = ["hello"]
                self.attr2 = 34

        data = dict(abc=[1, 2, 3], efg=dummy(), hij=(1.0, 2), klm=set([8, ()]))

        newdata = utilities.convert_object_tree(data, utilities.python_to_zodb_types)

        self.assertTrue(isinstance(newdata, utilities.PersistentDict))
        self.assertEqual(len(newdata), len(data))

        self.assertTrue(isinstance(newdata["abc"], utilities.PersistentList))
        self.assertTrue(isinstance(newdata["efg"], dummy))
        self.assertEqual(newdata["hij"], (1.0, 2)) # immutable sequences not touched !

        self.assertEqual(len(newdata["efg"].__dict__), 2)
        self.assertTrue(isinstance(newdata["efg"].attr1, utilities.PersistentList))
        self.assertTrue(isinstance(newdata["efg"].attr2, (int, long)))

        self.assertEqual(newdata["klm"], set([8, ()]))

        # back-conversion
        newnewdata = utilities.convert_object_tree(newdata, utilities.zodb_to_python_types)
        self.assertEqual(data, newnewdata)


        # test 2 #

        data = utilities.PersistentDict(abc=utilities.PersistentList([1, 2, 3]))

        newdata = utilities.convert_object_tree(data, utilities.zodb_to_python_types)

        self.assertTrue(isinstance(newdata, dict))

        self.assertTrue(isinstance(newdata["abc"], list))

        newnewdata = utilities.convert_object_tree(newdata, utilities.python_to_zodb_types)

        self.assertEqual(data, newnewdata)




    def test_yaml_fixture_loading(self):

        data = {"file1.yml": dedent("""
                                    characters:
                                        parent: "No data"
                                     """),
                "file2.yaml": dedent("""
                                     wap: 32
                                     """),
                "ignored.yl": "hello: 'hi'"}


        def _load_data(mydict):

            my_dir = tempfile.mkdtemp()
            print(">> temp dir", my_dir)

            for filename, file_data in mydict.items():
                with open(os.path.join(my_dir, filename), "w") as fd:
                    fd.write(file_data)

            return my_dir

        tmp_dir = _load_data(data)

        with pytest.raises(ValueError):
            utilities.load_yaml_fixture("/badpath")

        res = utilities.load_yaml_fixture(tmp_dir)
        assert res == {'characters': {'parent': 'No data'}, 'wap': 32}

        res = utilities.load_yaml_fixture(os.path.join(tmp_dir, "file1.yml"))
        assert res == {'characters': {'parent': 'No data'}}
        shutil.rmtree(tmp_dir)

        data.update({"file3.yml": "characters: 99"}) # collision
        tmp_dir = _load_data(data)
        with pytest.raises(ValueError):
            utilities.load_yaml_fixture("/badpath")
        shutil.rmtree(tmp_dir)


    def test_file_server_backends(self):

        path = os.path.join(config.GAME_FILES_ROOT, "README.txt")
        request = RequestFactory().get("/path/to/file.zip")

        kwargs = dict(save_as=random.choice((None, "othername.zip")),
                      size=random.choice((None, 1625726)),)

        def _check_standard_headers(response):
            if kwargs["save_as"]:
                assert kwargs["save_as"] in response["Content-Disposition"]
            if kwargs["size"]:
                assert response["Content-Length"] == str(kwargs["size"])

        response = fileservers.serve_file(request, path, **kwargs)
        assert response.content
        _check_standard_headers(response)

        response = fileservers.serve_file(request, path, backend_name="nginx", **kwargs)
        print (response._headers)
        assert response['X-Accel-Redirect'] == path
        assert not response.content
        _check_standard_headers(response)

        response = fileservers.serve_file(request, path, backend_name="xsendfile", **kwargs)
        assert not response.content
        assert response['X-Sendfile'] == path
        _check_standard_headers(response)


    def test_url_protection_functions(self):

        hash = hash_url_path("whatever/shtiff/kk.mp3?sssj=33")
        assert len(hash) == 8
        for c in hash:
            assert c in "abcdefghijklmnopqrstuvwxyz0123456789"

        rel_path = checked_game_file_path(game_file_url("/my/file/path"))
        assert rel_path == "my/file/path"

        rel_path = checked_game_file_path("http://baddomain/files/%s/my_file/a.jpg" % hash_url_path("my_file/a.jpg")) # we only care about PATH component of url
        assert rel_path == "my_file/a.jpg"

        assert checked_game_file_path("/bad/stuffs.mpg") is None
        assert checked_game_file_path(config.GAME_FILES_URL + "bad/stuffs.mpg") is None



    def test_rst_game_file_url_tags_handling(self):

        rst = dedent(r"""
        
                    [   GAME_FILE_URL 'myfile.jpg'    ] here
                    
                    .. image:: picture.jpeg [GAME_FILE_URL /a/cat/image.png]
                
                        [GAME_FILE_URL 'aa bb/cc']
                        
                        [GAME_FILE_URL "bad
                        path.jpg]
                    """)
        
        res = _generate_game_file_links(rst, self.dm)
        #print("\n@@@@@@\n", res)

        # WILL BREAK IF settings.SECRET_KEY IS CHANGED #
        assert res.strip() == dedent("""
                                /files/dfb1c549/myfile.jpg here

                                .. image:: picture.jpeg /files/92572209/a/cat/image.png
                                
                                    /files/8112d6b3/aa bb/cc
                                
                                    [GAME_FILE_URL "bad
                                    path.jpg]
                                """).strip()


    def test_rst_site_links_generation(self):

        # here we have: 1 bad view name, 2 good tags, and then an improperly formatted tag #
        rst = dedent(r"""
                    hi
                    
                    {% "hello" "kj.jjh" %}
                    
                    {% "good1" "pychronia_game.views.homepage" %}
                    
                    {% "good2" "view_sales" %}
                    
                    {% "bad\"string" "view_sales" %}
                    """)

        html = _generate_site_links(rst, self.dm)

        #print("------->", html)
        assert html.strip() == dedent(r"""
                                hi

                                hello
                                
                                <a href="/TeStiNg/">good1</a>
                                <a href="/TeStiNg/view_sales/">good2</a>
                                
                                {% "bad\"string" "view_sales" %}
                                """).strip()


    def test_enriched_text_behaviour(self):
        """
        We only test here that dependencies are well triggered, we don't test them precisely.
        """

        assert not self.dm.get_event_count("GENERATE_MESSAGING_LINKS")
        assert not self.dm.get_event_count("GENERATE_ENCYCLOPEDIA_LINKS")
        assert not self.dm.get_event_count("GENERATE_SITE_LINKS")
        assert not self.dm.get_event_count("GENERATE_GAME_FILE_LINKS")

        rst = dedent(r"""
                    hi
                    ---
                    
                    lokons
                    
                    gerbils
                    
                    [INSTANCE_ID]
                    
                    .. baddirective:: aaa
                    
                    hi[BR]you
                    """)
        html = _enriched_text(self.dm, rst, initial_header_level=2, report_level=5, excluded_link="lokon")

        assert self.dm.get_event_count("GENERATE_MESSAGING_LINKS") == 1
        assert self.dm.get_event_count("GENERATE_ENCYCLOPEDIA_LINKS") == 1
        assert self.dm.get_event_count("GENERATE_SITE_LINKS") == 1
        assert self.dm.get_event_count("GENERATE_GAME_FILE_LINKS") == 1

        assert "hi<br />you" in html # handy


        #print("------->", html)
        assert html.strip() == dedent("""
                            <div class="section" id="hi">
                            <h2>hi</h2>
                            <p>lokons</p>
                            <p><a href="/TeStiNg/encyclopedia/?search=gerbils">gerbils</a></p>
                            <p>TeStiNg</p>
                            <p>hi<br />you</p>
                            </div>""").strip()


        rst = dedent(r"""
                    hello
                    ======
                    
                    .. baddirective:: aaa
                    
                    """)
        html = _enriched_text(self.dm, rst)  # we ensure NO PERSISTENCE of previously set options!!

        #print("------->", html)

        assert html.strip() == dedent("""
                                    <div class="section" id="hello">
                                    <h2>hello</h2>
                                    <div class="system-message">
                                    <p class="system-message-title">System Message: ERROR/3 (<tt class="docutils">&lt;string&gt;</tt>, line 5)</p>
                                    <p>Unknown directive type &quot;baddirective&quot;.</p>
                                    <pre class="literal-block">
                                    .. baddirective:: aaa
                                    
                                    </pre>
                                    </div>
                                    </div>
                                    """).strip()



class TestMetaAdministration(unittest.TestCase): # no django setup required ATM

    def test_game_instance_management_api(self):

        check_zodb_structure()

        game_instance_id = "mystuff"
        assert not game_instance_exists(game_instance_id)
        create_game_instance(game_instance_id, "aaa@sc.com", "master", "pwd")
        assert game_instance_exists(game_instance_id)

        dm = retrieve_game_instance(game_instance_id)
        assert dm.is_initialized
        assert dm.data

        delete_game_instance(game_instance_id)
        assert not game_instance_exists(game_instance_id)
        with pytest.raises(ValueError):
            retrieve_game_instance(game_instance_id)




# TODO - test that messages are well propagated through session
# TODO - test interception of "POST" when impersonating user


class TestDatamanager(BaseGameTestCase):


    def test_public_method_wrapping(self):

        # TODO FIXME - extend this check action methods of all ABILITIES !!! FIXME

        for attr in dir(GameDataManager):
            if attr.startswith("_") or attr in "begin rollback commit close check_no_pending_transaction is_in_transaction".split():
                continue

            # we remove class/static methods, and some utilities that don't need decorators.
            if attr in ("""
                        notify_event get_event_count clear_event_stats clear_all_event_stats
                        
                        register_permissions register_ability register_game_view get_abilities 
                        get_activable_views get_game_views instantiate_ability instantiate_game_view
                        """.split()):
                continue

            obj = getattr(GameDataManager, attr)
            if not inspect.isroutine(obj):
                continue

            if not getattr(obj, "_is_under_transaction_watcher", None) \
                and not getattr(obj, "_is_under_readonly_method", None):
                raise AssertionError("Undecorated public datamanager method: %s" % obj)


        assert GameDataManager.process_secret_answer_attempt._is_always_writable == False # sensible DEFAULT
        assert GameDataManager.access_novelty._is_always_writable == False
        assert GameDataManager.mark_current_playlist_read._is_always_writable == False

        assert GameDataManager.set_game_state._is_always_writable == True # even if master bypasses constraints here
        assert GameDataManager.sync_game_view_data._is_always_writable == True
        assert GameDataManager.set_message_read_state._is_always_writable == True



    @for_datamanager_base
    def test_requestless_datamanager(self):

        assert self.dm.request
        self.dm._request = None
        assert self.dm.request is None # property

        # user notifications get swallowed
        user = self.dm.user
        user.add_message("sqdqsd sss")
        user.add_error("fsdfsdf")
        assert user.get_notifications() == []
        assert not user.has_notifications()
        user.discard_notifications()


    @for_datamanager_base
    def test_modular_architecture(self):

        assert len(MODULES_REGISTRY) > 4

        for core_module in MODULES_REGISTRY:

            # we ensure every module calls super() properly

            CastratedDataManager = type(str('Dummy' + core_module.__name__), (core_module,), {})
            castrated_dm = CastratedDataManager.__new__(CastratedDataManager) # we bypass __init__() call there
            utilities.TechnicalEventsMixin.__init__(castrated_dm) # only that mixing gets initizalized

            try:
                root = _get_zodb_connection().root()
                my_id = str(random.randint(1, 10000))
                root[my_id] = PersistentDict()
                castrated_dm.__init__(game_instance_id=my_id,
                                      game_root=root[my_id],
                                      request=self.request)
            except Exception, e:
                transaction.abort()
            assert castrated_dm.get_event_count("BASE_DATA_MANAGER_INIT_CALLED") == 1

            try:
                castrated_dm._init_from_db()
            except Exception, e:
                transaction.abort()
            assert castrated_dm.get_event_count("BASE_DATA_MANAGER_INIT_FROM_DB_CALLED") == 1

            try:
                castrated_dm._load_initial_data()
            except Exception, e:
                transaction.abort()
            assert castrated_dm.get_event_count("BASE_LOAD_INITIAL_DATA_CALLED") == 1

            try:
                castrated_dm._check_database_coherency()
            except Exception, e:
                transaction.abort()
            assert castrated_dm.get_event_count("BASE_CHECK_DB_COHERENCY_PRIVATE_CALLED") == 1

            try:
                report = PersistentList()
                castrated_dm._process_periodic_tasks(report)
            except Exception, e:
                transaction.abort()
            assert castrated_dm.get_event_count("BASE_PROCESS_PERIODIC_TASK_CALLED") == 1


    @for_core_module(FlexibleTime)
    def test_permission_handling(self):

        assert self.dm.build_permission_select_choices()
        assert "purchase_confidentiality_protection" in self.dm.PERMISSIONS_REGISTRY # EXTRA_PERMISSIONS system

        permission = "access_world_scan" # exists because REQUIRES_CHARACTER_PERMISSION=True
        assert permission in self.dm.PERMISSIONS_REGISTRY

        self._set_user("guy1")
        assert not self.dm.has_permission(permission=permission)
        self.dm.update_permissions(permissions=[permission])
        assert self.dm.has_permission(permission=permission)
        assert self.dm.user.has_permission(permission)
        self.dm.update_permissions(permissions=[])
        assert not self.dm.has_permission(username="guy1", permission=permission)
        assert not self.dm.user.has_permission(permission)

        self._set_user("guy3")
        assert not self.dm.has_permission(permission=permission)
        self.dm.update_allegiances(allegiances=["sciences"]) # has that "permission"
        assert self.dm.has_permission(permission=permission)
        self.dm.update_permissions(permissions=[permission])
        assert self.dm.has_permission(permission=permission) # permission both personally and via allegiance
        assert self.dm.user.has_permission(permission)
        self.dm.update_allegiances(allegiances=[])
        assert self.dm.has_permission(permission=permission) # still personally
        self.dm.update_permissions(permissions=[])
        assert not self.dm.has_permission(permission=permission)
        assert not self.dm.user.has_permission(permission)


    @for_core_module(FlexibleTime)
    def test_flexible_time_module(self):

        game_length = 45.3 # test fixture
        assert self.dm.get_global_parameter("game_theoretical_length_days") == game_length

        self.assertRaises(Exception, self.dm.compute_effective_remote_datetime, (3, 2))

        for value in [0.025 / game_length, (0.02 / game_length, 0.03 / game_length)]: # beware of the rounding to integer seconds...

            now = datetime.utcnow()
            dt = self.dm.compute_effective_remote_datetime(value)
            assert now + timedelta(seconds=1) <= dt <= now + timedelta(seconds=2), (now, dt)

            self.assertEqual(utilities.is_past_datetime(dt), False)
            time.sleep(0.5)
            self.assertEqual(utilities.is_past_datetime(dt), False)
            time.sleep(2)
            self.assertEqual(utilities.is_past_datetime(dt), True)

            utc = datetime.utcnow()
            now = datetime.now()
            now2 = utilities.utc_to_local(utc)
            self.assertTrue(now - timedelta(seconds=1) < now2 < now + timedelta(seconds=1))


    @for_core_module(CurrentUserHandling)
    def test_game_writability_summarizer(self):

        self._set_user("guy1")
        res = self.dm.determine_actual_game_writability()
        assert res == dict(writable=True,
                            reason=None)

        self.dm.propose_friendship("guy1", "guy2")
        self.dm.propose_friendship("guy2", "guy1")
        self._set_user(random.choice(("master", "guy2")), impersonation_target="guy1", impersonation_writability=False)
        res = self.dm.determine_actual_game_writability()
        assert not res["writable"]
        assert res["reason"]
        assert not self.dm.is_game_writable()

        self.dm.set_game_state(False)

        self._set_user("master")
        res = self.dm.determine_actual_game_writability()
        assert res["writable"]
        assert not res["reason"]
        assert self.dm.is_game_writable()

        self._set_user("guy1")
        res = self.dm.determine_actual_game_writability()
        assert not res["writable"]
        assert res["reason"]
        assert not self.dm.is_game_writable()




    @for_core_module(CharacterHandling)
    def test_character_handling(self):
        assert self.dm.update_real_life_data("guy1", real_life_identity="jjjj")
        assert self.dm.update_real_life_data("guy1", real_life_email="ss@pangea.com")
        data = self.dm.get_character_properties("guy1")
        assert data["real_life_identity"] == "jjjj"
        assert data["real_life_email"] == "ss@pangea.com"
        assert self.dm.update_real_life_data("guy1", real_life_identity="kkkk", real_life_email="kkkk@pangea.com")
        assert data["real_life_identity"] == "kkkk"
        assert data["real_life_email"] == "kkkk@pangea.com"
        assert not self.dm.update_real_life_data("guy1", real_life_identity="", real_life_email=None)
        assert data["real_life_identity"] == "kkkk"
        assert data["real_life_email"] == "kkkk@pangea.com"
        assert self.dm.get_character_color_or_none("guy1") == "#0033CC"
        assert self.dm.get_character_color_or_none("unexistinguy") is None
        assert self.dm.get_character_color_or_none("") is None
        with pytest.raises(UsageError):
            self.dm.update_real_life_data("unexistinguy", real_life_identity="John")
        with pytest.raises(UsageError):
            self.dm.update_real_life_data("guy1", real_life_email="bad_email")

        self._set_user("guy1")
        res1 = self.dm.get_character_usernames()
        assert "guy1" in res1
        res2 = self.dm.get_character_usernames(exclude_current=True)
        assert "guy1" not in res2
        assert len(res2) == len(res1) - 1

        self._set_user("master")
        assert self.dm.get_character_usernames(exclude_current=True) == self.dm.get_character_usernames() # no crash if not a proper character currently set
        self._set_user(None)
        assert self.dm.get_character_usernames(exclude_current=True) == self.dm.get_character_usernames() # no crash if not a proper character currently set



    @for_core_module(DomainHandling)
    def test_domain_handling(self):

        self.dm.update_allegiances("guy1", [])

        assert self.dm.update_allegiances("guy1", ["sciences"]) == (["sciences"], [])
        assert self.dm.update_allegiances("guy1", []) == ([], ["sciences"])
        assert self.dm.update_allegiances("guy1", ["sciences", "acharis"]) == (["acharis", "sciences"], []) # sorted
        assert self.dm.update_allegiances("guy1", ["sciences", "acharis"]) == ([], []) # no changes

        with pytest.raises(UsageError):
            self.dm.update_allegiances("guy1", ["dummydomain"])

        with pytest.raises(UsageError):
            self.dm.update_real_life_data("unexistinguy", real_life_identity=["sciences"])


    @for_core_module(FriendshipHandling)
    def test_friendship_handling(self):

        dm = self.dm

        dm.reset_friendship_data()

        full = self.dm.get_full_friendship_data()
        assert isinstance(full, (dict, PersistentDict))
        assert "sealed" in full and "proposed" in full


        assert self.dm.get_other_characters_friendship_statuses("guy1") == {u'guy2': None, 'guy3': None, 'guy4': None}
        assert self.dm.get_other_characters_friendship_statuses("guy2") == {u'guy1': None, 'guy3': None, 'guy4': None}

        assert not dm.data["friendships"]["proposed"]
        assert not dm.data["friendships"]["sealed"]

        with pytest.raises(AbnormalUsageError):
            dm.propose_friendship(dm.anonymous_login, "guy1")
        with pytest.raises(AbnormalUsageError):
            dm.propose_friendship("guy1", dm.anonymous_login)
        with pytest.raises(AbnormalUsageError):
            dm.propose_friendship("guy1", "guy1") # auto-friendship impossible

        assert not dm.propose_friendship("guy2", "guy1") # proposes
        assert not dm.are_friends("guy1", "guy2")
        assert not dm.are_friends("guy2", "guy1")
        assert not dm.are_friends("guy1", "guy3")

        assert self.dm.get_other_characters_friendship_statuses("guy1") == {u'guy2': 'requested_by', 'guy3': None, 'guy4': None}
        assert self.dm.get_other_characters_friendship_statuses("guy2") == {u'guy1': 'proposed_to', 'guy3': None, 'guy4': None}

        # friendship proposals don't impact impersonation
        assert not self.dm.can_impersonate("guy1", "guy3")
        assert not self.dm.can_impersonate("guy1", "guy2")
        assert not self.dm.can_impersonate("guy2", "guy1")

        with pytest.raises(AbnormalUsageError):
            dm.propose_friendship("guy2", "guy1") # friendship already requested

        assert dm.data["friendships"]["proposed"]
        assert not dm.data["friendships"]["sealed"]

        with pytest.raises(AbnormalUsageError):
            dm.propose_friendship("guy2", "guy1") # duplicate proposal

        assert dm.get_friendship_requests_for_character("guy3") == dict(proposed_to=[],
                                                          requested_by=[])
        assert dm.get_friendship_requests_for_character("guy1") == dict(proposed_to=[],
                                                          requested_by=["guy2"])
        assert dm.get_friendship_requests_for_character("guy2") == dict(proposed_to=["guy1"],
                                                          requested_by=[])
        time.sleep(0.5)
        assert dm.propose_friendship("guy1", "guy2") # we seal friendship, here

        # friends can impersonate each other!
        assert not self.dm.can_impersonate("guy1", "guy3")
        assert self.dm.can_impersonate("guy1", "guy2")
        assert self.dm.can_impersonate("guy2", "guy1")

        assert self.dm.get_other_characters_friendship_statuses("guy1") == {u'guy2': 'recent_friend', 'guy3': None, 'guy4': None}
        assert self.dm.get_other_characters_friendship_statuses("guy2") == {u'guy1': 'recent_friend', 'guy3': None, 'guy4': None}

        with pytest.raises(AbnormalUsageError):
            dm.propose_friendship("guy2", "guy1") # already friends
        with pytest.raises(AbnormalUsageError):
            dm.propose_friendship("guy1", "guy2") # already friends

        assert not dm.data["friendships"]["proposed"]
        assert dm.data["friendships"]["sealed"].keys() == [("guy2", "guy1")] # order is "first proposer first"

        key, params = dm.get_friendship_params("guy1", "guy2")
        key_bis, params_bis = dm.get_friendship_params("guy2", "guy1")
        assert key == key_bis == ("guy2", "guy1") # order OK
        assert params == params_bis
        assert datetime.utcnow() - timedelta(seconds=5) <= params["proposal_date"] <= datetime.utcnow()
        assert datetime.utcnow() - timedelta(seconds=5) <= params["acceptance_date"] <= datetime.utcnow()
        assert params["proposal_date"] < params["acceptance_date"]

        with pytest.raises(AbnormalUsageError):
            dm.get_friendship_params("guy1", "guy3")
        with pytest.raises(AbnormalUsageError):
            dm.get_friendship_params("guy3", "guy1")
        with pytest.raises(AbnormalUsageError):
            dm.get_friendship_params("guy3", "guy4")

        assert dm.are_friends("guy2", "guy1") == dm.are_friends("guy1", "guy2") == True
        assert dm.are_friends("guy2", "guy3") == dm.are_friends("guy3", "guy4") == False

        assert not dm.propose_friendship("guy2", "guy3") # proposed
        with pytest.raises(AbnormalUsageError):
            dm.terminate_friendship("guy3", "guy2") # wrong direction
        assert not dm.terminate_friendship("guy2", "guy3") # abort proposal, actually

        assert not dm.propose_friendship("guy2", "guy3") # proposed
        assert dm.propose_friendship("guy3", "guy2") # accepted
        assert dm.get_friends_for_character("guy1") == dm.get_friends_for_character("guy3") == ["guy2"]
        assert dm.get_friends_for_character("guy2") in (["guy1", "guy3"], ["guy3", "guy1"]) # order not enforced
        assert dm.get_friends_for_character("guy4") == []

        assert self.dm.get_other_characters_friendship_statuses("guy1") == {u'guy2': 'recent_friend', 'guy3': None, 'guy4': None}
        assert self.dm.get_other_characters_friendship_statuses("guy2") == {u'guy1': 'recent_friend', 'guy3': 'recent_friend', 'guy4': None}

        with pytest.raises(AbnormalUsageError):
            dm.terminate_friendship("guy3", "guy4") # unexisting friendship
        with pytest.raises(AbnormalUsageError):
            dm.terminate_friendship("guy1", "guy2") # too young friendship

        # old friendship still makes impersonation possible of course
        assert not self.dm.can_impersonate("guy1", "guy3")
        assert self.dm.can_impersonate("guy1", "guy2")
        assert self.dm.can_impersonate("guy2", "guy1")

        for pair, params in dm.data["friendships"]["sealed"].items():
            if "guy1" in pair:
                params["acceptance_date"] -= timedelta(hours=30) # delay should be 24h in dev
                dm.commit()

        assert self.dm.get_other_characters_friendship_statuses("guy1") == {u'guy2': 'old_friend', 'guy3': None, 'guy4': None}
        assert self.dm.get_other_characters_friendship_statuses("guy2") == {u'guy1': 'old_friend', 'guy3': 'recent_friend', 'guy4': None}

        assert dm.terminate_friendship("guy1", "guy2") # success

        # no more friends -> no more impersonation
        assert not self.dm.can_impersonate("guy1", "guy3")
        assert not self.dm.can_impersonate("guy1", "guy2")
        assert not self.dm.can_impersonate("guy2", "guy1")

        assert not dm.are_friends("guy2", "guy1")
        with pytest.raises(UsageError):
            dm.get_friendship_params("guy1", "guy2")
        assert dm.are_friends("guy2", "guy3") # untouched

        assert self.dm.get_other_characters_friendship_statuses("guy1") == {u'guy2': None, 'guy3': None, 'guy4': None}
        assert self.dm.get_other_characters_friendship_statuses("guy2") == {u'guy1': None, 'guy3': 'recent_friend', 'guy4': None}
        assert self.dm.get_other_characters_friendship_statuses("guy3") == {u'guy1': None, 'guy2': 'recent_friend', 'guy4': None}
        assert self.dm.get_other_characters_friendship_statuses("guy4") == {u'guy1': None, 'guy2': None, 'guy3': None}

        dm.reset_friendship_data()
        assert not dm.data["friendships"]["proposed"]
        assert not dm.data["friendships"]["sealed"]
        assert not dm.get_friends_for_character("guy1")
        assert not dm.get_friends_for_character("guy2")
        assert not dm.get_friends_for_character("guy3")
        assert not dm.are_friends("guy2", "guy1")
        assert not dm.are_friends("guy3", "guy2")
        assert not dm.are_friends("guy3", "guy4")


    @for_core_module(OnlinePresence)
    def test_online_presence(self):

        self.dm.data["global_parameters"]["online_presence_timeout_s"] = 1
        self.dm.data["global_parameters"]["chatroom_presence_timeout_s"] = 1
        self.dm.commit()

        time.sleep(1.2)

        self.assertFalse(self.dm.get_online_status("guy1"))
        self.assertFalse(self.dm.get_online_status("guy2"))
        self.assertFalse(self.dm.get_chatting_status("guy1"))
        self.assertFalse(self.dm.get_chatting_status("guy2"))
        self.assertEqual(self.dm.get_online_users(), [])
        self.assertEqual(self.dm.get_chatting_users(), [])

        self.dm.set_online_status("guy1")

        self.assertTrue(self.dm.get_online_status("guy1"))
        self.assertFalse(self.dm.get_online_status("guy2"))
        self.assertFalse(self.dm.get_chatting_status("guy1"))
        self.assertFalse(self.dm.get_chatting_status("guy2"))
        self.assertEqual(self.dm.get_online_users(), ["guy1"])
        self.assertEqual(self.dm.get_chatting_users(), [])

        time.sleep(1.2)

        self.dm._set_chatting_status("guy2")
        self.dm.commit()

        self.assertFalse(self.dm.get_online_status("guy1"))
        self.assertTrue(self.dm.get_online_status("guy2")) # propagated too
        self.assertFalse(self.dm.get_chatting_status("guy1"))
        self.assertTrue(self.dm.get_chatting_status("guy2"))
        self.assertEqual(self.dm.get_online_users(), ["guy2"])
        self.assertEqual(self.dm.get_chatting_users(), ["guy2"])
        self.assertEqual(self.dm.get_chatting_users(exclude_current=True), ["guy2"])

        self._set_user("guy2")
        self.assertEqual(self.dm.get_chatting_users(), ["guy2"])
        self.assertEqual(self.dm.get_chatting_users(exclude_current=True), [])

        time.sleep(1.2)

        self.dm.get_chatroom_messages(from_slice_index=0)
        self.assertFalse(self.dm.get_online_status("guy1"))
        self.assertTrue(self.dm.get_online_status("guy2")) # UP for online presence
        self.assertFalse(self.dm.get_chatting_status("guy1"))
        self.assertTrue(self.dm.get_chatting_status("guy2")) # just fetching msgs does update chatting presence
        self.assertEqual(self.dm.get_online_users(), ["guy2"])
        self.assertEqual(self.dm.get_chatting_users(), ["guy2"])


        time.sleep(1.2)

        self.assertFalse(self.dm.get_online_status("guy1"))
        self.assertFalse(self.dm.get_online_status("guy2"))
        self.assertFalse(self.dm.get_chatting_status("guy1"))
        self.assertFalse(self.dm.get_chatting_status("guy2"))
        self.assertEqual(self.dm.get_online_users(), [])
        self.assertEqual(self.dm.get_chatting_users(), [])


    # todo - refactor this ?
    def test_misc_getters_setters(self):
        self._reset_messages()

        self.assertEqual(self.dm.get_username_from_official_name(self.dm.get_official_name("guy2")), "guy2")

        # DEPRECATED self.assertEqual(self.dm.get_fellow_usernames("guy2"), ["guy1"])

        self.assertEqual(len(self.dm.get_game_instructions("guy2")), 3)

        self.dm.set_game_state(started=False)
        self.assertEqual(self.dm.is_game_started(), False)
        self.dm.set_game_state(started=True)
        self.assertEqual(self.dm.is_game_started(), True)

        self.assertEqual(self.dm.get_username_from_email("qdqsdqd@dqsd.fr"), self.dm.get_global_parameter("master_login"))
        self.assertEqual(self.dm.get_username_from_email("guy1@pangea.com"), "guy1")


        self._set_user("master")


        # we test global parameter handling here...
        self.dm.set_global_parameter("game_theoretical_length_days", 22)
        assert self.dm.get_global_parameter("game_theoretical_length_days") == 22

        with pytest.raises(AbnormalUsageError):
            self.dm.set_global_parameter("unexisting_param", 33)





    @for_core_module(MoneyItemsOwnership)
    def test_item_transfers(self):
        self._reset_messages()

        lg_old = copy.deepcopy(self.dm.get_character_properties("guy3"))
        nw_old = copy.deepcopy(self.dm.get_character_properties("guy1"))
        items_old = copy.deepcopy(self.dm.get_all_items())
        bank_old = self.dm.get_global_parameter("bank_account")

        gem_names = [key for key, value in items_old.items() if value["is_gem"] and value["num_items"] >= 3] # we only take numerous groups
        object_names = [key for key, value in items_old.items() if not value["is_gem"]]

        gem_name1 = gem_names[0]
        gem_name2 = gem_names[1] # wont be sold
        object_name = object_names[0]
        bank_name = self.dm.get_global_parameter("bank_name")

        self.assertRaises(UsageError, self.dm.transfer_money_between_characters, bank_name, "guy1", 10000000)
        self.assertRaises(UsageError, self.dm.transfer_money_between_characters, "guy3", "guy1", -100)
        self.assertRaises(UsageError, self.dm.transfer_money_between_characters, "guy3", "guy1", 0)
        self.assertRaises(UsageError, self.dm.transfer_money_between_characters, "guy3", "guy1", lg_old["account"] + 1) # too much
        self.assertRaises(UsageError, self.dm.transfer_money_between_characters, "guy3", "guy3", 1) # same ids
        self.assertRaises(UsageError, self.dm.transfer_object_to_character, "dummy_name", "guy3") # shall NOT happen
        self.assertRaises(UsageError, self.dm.transfer_object_to_character, object_name, "dummy_name")


        # data mustn't have changed when raising exceptions
        self.assertEqual(self.dm.get_character_properties("guy3"), lg_old)
        self.assertEqual(self.dm.get_character_properties("guy1"), nw_old)
        self.assertEqual(self.dm.get_all_items(), items_old)
        self.assertEqual(self.dm.get_global_parameter("bank_account"), bank_old)

        # we check that real operations work OK
        self.dm.transfer_object_to_character(gem_name1, "guy3")
        self.dm.transfer_object_to_character(object_name, "guy3")
        self.dm.transfer_money_between_characters("guy3", "guy1", 100)

        self.dm.transfer_money_between_characters("guy3", "bank", 100)
        self.assertEqual(self.dm.get_global_parameter("bank_account"), bank_old + 100)
        self.assertEqual(self.dm.get_character_properties("guy3")["account"], lg_old["account"] - 200) # 100 to guy1 + 100 to bank
        self.dm.transfer_money_between_characters("bank", "guy3", 100)
        self.assertEqual(self.dm.get_global_parameter("bank_account"), bank_old)

        # we fully test gems transfers
        gems_given = self.dm.get_character_properties("guy3")["gems"][0:3]
        self.dm.transfer_gems_between_characters("guy3", "guy1", gems_given)
        self.dm.transfer_gems_between_characters("guy1", "guy3", gems_given)
        self.assertRaises(UsageError, self.dm.transfer_gems_between_characters, "guy3", "guy3", gems_given) # same ids
        self.assertRaises(UsageError, self.dm.transfer_gems_between_characters, "guy3", "guy1", gems_given + [27, 32]) # not possessed
        self.assertRaises(UsageError, self.dm.transfer_gems_between_characters, "guy3", "guy1", []) # at least 1 gem needed

        items_new = copy.deepcopy(self.dm.get_all_items())
        lg_new = self.dm.get_character_properties("guy3")
        nw_new = self.dm.get_character_properties("guy1")
        assert set(self.dm.get_available_items_for_user("guy3").keys()) == set([gem_name1, object_name])
        self.assertEqual(lg_new["gems"], [(items_new[gem_name1]["unit_cost"], gem_name1)] * items_new[gem_name1]["num_items"])
        self.assertEqual(items_new[gem_name1]["owner"], "guy3")
        self.assertEqual(items_new[object_name]["owner"], "guy3")
        self.assertEqual(lg_new["account"], lg_old["account"] - 100)
        self.assertEqual(nw_new["account"], nw_old["account"] + 100)


        # PREVIOUS OWNER CHECKING (it's currently guy3)
        for previous_owner in (self.dm.master_login, self.dm.anonymous_login, "guy1", "guy2"):
            with pytest.raises(UsageError):
                self.dm.transfer_object_to_character(object_name, "guy2", previous_owner=previous_owner)
        self.dm.transfer_object_to_character(object_name, "guy2", previous_owner="guy3")
        assert self.dm.get_user_artefacts("guy2").keys() == [object_name]
        assert self.dm.get_user_artefacts("guy3") == {}
        self.dm.transfer_object_to_character(object_name, "guy3", previous_owner="guy2") # we undo just this


        # we test possible and impossible undo operations

        self.assertRaises(Exception, self.dm.transfer_object_to_character, gem_name2, None) # same ids - already free item

        # check no changes occured
        self.assertEqual(self.dm.get_character_properties("guy3"), self.dm.get_character_properties("guy3"))
        self.assertEqual(self.dm.get_character_properties("guy1"), self.dm.get_character_properties("guy1"))
        self.assertEqual(self.dm.get_all_items(), items_new)

        # undoing item sales
        self.assertRaises(Exception, self.dm.transfer_object_to_character, gem_name1, "guy3") # same ids - same current owner and target
        self.dm.transfer_object_to_character(gem_name1, None)
        self.dm.transfer_object_to_character(object_name, None)
        items_new = copy.deepcopy(self.dm.get_all_items())
        self.assertEqual(items_new[gem_name1]["owner"], None)
        self.assertEqual(items_new[object_name]["owner"], None)
        self.dm.transfer_money_between_characters("guy1", "guy3", 100)

        # we're back to initial state
        self.assertEqual(self.dm.get_character_properties("guy3"), lg_old)
        self.assertEqual(self.dm.get_character_properties("guy1"), nw_old)
        self.assertEqual(self.dm.get_all_items(), items_old)

        # undo failure
        self.dm.transfer_object_to_character(gem_name1, "guy3")
        gem = self.dm.get_character_properties("guy3")["gems"].pop()
        self.dm.commit()
        with pytest.raises(UsageError) as exc_info:
            self.dm.transfer_object_to_character(gem_name1, random.choice(("guy1", None))) # one gem is lacking, so...
        assert "already been used" in str(exc_info.value)

        self.dm.get_character_properties("guy3")["gems"].append(gem)
        self.dm.commit()
        self.dm.transfer_object_to_character(gem_name1, None)

        self.assertEqual(self.dm.get_character_properties("guy3"), lg_old)
        self.assertEqual(self.dm.get_character_properties("guy1"), nw_old)
        self.assertEqual(self.dm.get_all_items(), items_old)





    @for_core_module(MoneyItemsOwnership)
    def test_available_items_listing(self):
        self._reset_messages()

        self._set_user("guy1")

        # print (">>>", self.dm.__class__.__mro__)
        all_items = self.dm.get_all_items()
        gems = self.dm.get_gem_items()
        artefacts = self.dm.get_non_gem_items()

        assert set(all_items.keys()) == set(gems.keys()) | set(artefacts.keys())
        assert not (set(gems.keys()) & set(artefacts.keys()))

        auctions = self.dm.get_auction_items()
        for it in auctions.values():
            assert it["auction"]

        items_old = copy.deepcopy(self.dm.get_all_items())
        gem_names = [key for key, value in items_old.items() if value["is_gem"] and value["num_items"] >= 3] # we only take numerous groups
        object_names = [key for key, value in items_old.items() if not value["is_gem"]]

        gem_name1 = gem_names[0]
        gem_name2 = gem_names[1]
        object_name = object_names[0]

        self.dm.transfer_object_to_character(gem_name1, "guy2")
        self.dm.transfer_object_to_character(gem_name2, "guy2")
        self.dm.transfer_object_to_character(object_name, "guy3")

        self.assertEqual(self.dm.get_available_items_for_user("master"), self.dm.get_all_items())
        self.assertEqual(set(self.dm.get_available_items_for_user("guy1").keys()), set([]))
        self.assertNotEqual(self.dm.get_available_items_for_user("guy2"), self.dm.get_available_items_for_user("guy1")) # no sharing of objects, even shared allegiance
        self.assertEqual(set(self.dm.get_available_items_for_user("guy2").keys()), set([gem_name1, gem_name2]))
        self.assertEqual(set(self.dm.get_available_items_for_user("guy3").keys()), set([object_name]))

        assert self.dm.get_user_artefacts() == {} # guy1
        assert self.dm.get_user_artefacts("guy1") == {}
        assert self.dm.get_user_artefacts("guy2") == {} # gems NOT included
        assert self.dm.get_user_artefacts("guy3").keys() == [object_name]




    @for_core_module(PersonalFiles)
    def test_personal_files(self):
        self._reset_messages()

        files1 = self.dm.get_personal_files("guy2", absolute_urls=True)
        self.assertTrue(len(files1))
        self.assertTrue(files1[0].startswith("http"))

        files1bis = self.dm.get_personal_files("guy2")
        self.assertEqual(len(files1), len(files1bis))
        self.assertTrue(files1bis[0].startswith("/"))

        files2 = self.dm.get_personal_files(self.dm.master_login) # private game master files
        self.assertTrue(files2)

        c = Client() # file retrievals
        response = c.get(files1[0])
        self.assertEqual(response.status_code, 200)
        response = c.get(files1bis[0])
        self.assertEqual(response.status_code, 200)
        response = c.get(files1bis[0] + ".dummy")
        self.assertEqual(response.status_code, 404)

        for username in self.dm.get_character_usernames():
            self.dm.get_personal_files(username, absolute_urls=random.choice([True, False]))


    @for_core_module(PersonalFiles)
    def test_encrypted_folders(self):
        self._reset_messages()

        self.assertTrue(self.dm.encrypted_folder_exists("guy2_report"))
        self.assertFalse(self.dm.encrypted_folder_exists("dummyarchive"))

        self.assertRaises(dm_module.UsageError, self.dm.get_encrypted_files, "hacker", "dummyarchive", "bagheera")
        self.assertRaises(dm_module.UsageError, self.dm.get_encrypted_files, "hacker", "guy2_report", "badpassword")

        files = self.dm.get_encrypted_files("badusername", "guy2_report", "schamaalamoktuhg", absolute_urls=True) # no error raised for bad username !
        self.assertTrue(files, files)

        files1 = self.dm.get_encrypted_files("hacker", "guy2_report", "evans", absolute_urls=True)
        self.assertTrue(files1, files1)
        files2 = self.dm.get_encrypted_files("hacker", "guy2_report", "evans", absolute_urls=False)
        self.assertEqual(len(files1), len(files2))

        c = Client() # file retrievals
        response = c.get(files1[0])
        self.assertEqual(response.status_code, 200, (response.status_code, files1[0]))
        response = c.get(files2[0])
        self.assertEqual(response.status_code, 200)
        response = c.get(files2[0] + ".dummy")
        self.assertEqual(response.status_code, 404)


    @for_core_module(Encyclopedia)
    def test_encyclopedia(self):

        utilities.check_is_restructuredtext(self.dm.get_encyclopedia_entry(" gerbiL_speCies ")) # tolerant fetching
        assert self.dm.get_encyclopedia_entry("qskiqsjdqsid") is None
        assert "gerbil_species" in self.dm.get_encyclopedia_article_ids()

        assert ("animals?", ["lokon", "gerbil_species"]) in self.dm.get_encyclopedia_keywords_mapping().items()
        assert ("animals?", ["lokon"]) in self.dm.get_encyclopedia_keywords_mapping(excluded_link="gerbil_species").items() # no links to currently viewed article

        for entry in self.dm.get_encyclopedia_keywords_mapping().keys():
            utilities.check_is_slug(entry)
            assert entry.lower() == entry

        # best matches
        assert self.dm.get_encyclopedia_matches("qssqs") == []
        assert self.dm.get_encyclopedia_matches("hiqqsd bAdgerbilZ") == ["gerbil_species"] # we're VERY tolerant
        assert self.dm.get_encyclopedia_matches("rodEnt") == ["gerbil_species"]
        assert self.dm.get_encyclopedia_matches("hi gerbils animaL") == ["gerbil_species", "lokon"]
        assert self.dm.get_encyclopedia_matches("animal loKon") == ["lokon", "gerbil_species"]
        assert self.dm.get_encyclopedia_matches(u"animéàk") == [u"wu\\gly_é"]


        # index available or not ?
        assert not self.dm.is_encyclopedia_index_visible()
        not self.dm.set_encyclopedia_index_visibility(True)
        assert self.dm.is_encyclopedia_index_visible()
        not self.dm.set_encyclopedia_index_visibility(False)
        assert not self.dm.is_encyclopedia_index_visible()

        # generation of entry links
        res = _generate_encyclopedia_links("lokon lokons lokonsu", self.dm)
        expected = """<a href="@@@?search=lokon">lokon</a> <a href="@@@?search=lokons">lokons</a> lokonsu"""
        expected = expected.replace("@@@", reverse(views.view_encyclopedia, kwargs=dict(game_instance_id=self.dm.game_instance_id)))
        assert res == expected

        res = _generate_encyclopedia_links(u"""wu\\gly_é gerbil \n lokongerbil dummy gerb\nil <a href="#">lokon\n</a> lokons""", self.dm)
        print (repr(res))
        expected = u'wu\\gly_é <a href="@@@?search=gerbil">gerbil</a> \n lokongerbil dummy gerb\nil <a href="#">lokon\n</a> <a href="@@@?search=lokons">lokons</a>'
        expected = expected.replace("@@@", reverse(views.view_encyclopedia, kwargs=dict(game_instance_id=self.dm.game_instance_id)))
        assert res == expected

        res = _generate_encyclopedia_links(u"""i<à hi""", self.dm)
        print (repr(res))
        expected = u'<a href="/TeStiNg/encyclopedia/?search=i%3C%C3%A0">i&lt;\xe0</a> hi'
        expected = expected.replace("@@@", reverse(views.view_encyclopedia, kwargs=dict(game_instance_id=self.dm.game_instance_id)))
        assert res == expected


        # knowledge of article ids #

        for unauthorized in ("master", None):
            self._set_user(unauthorized)
            with pytest.raises(UsageError):
                self.dm.get_character_known_article_ids()
            with pytest.raises(UsageError):
                self.dm.update_character_known_article_ids(article_ids=["lokon"])
            with pytest.raises(UsageError):
                self.dm.reset_character_known_article_ids()

        self._set_user("guy1")
        assert self.dm.get_character_known_article_ids() == []
        self.dm.update_character_known_article_ids(article_ids=["lokon"])
        assert self.dm.get_character_known_article_ids() == ["lokon"]
        self.dm.update_character_known_article_ids(article_ids=["gerbil_species", "unexisting", "lokon", "gerbil_species"])
        assert self.dm.get_character_known_article_ids() == ["lokon", "gerbil_species", "unexisting"]
        self.dm.reset_character_known_article_ids()
        assert self.dm.get_character_known_article_ids() == []


    def test_message_automated_state_changes(self):
        self._reset_messages()

        email = self.dm.get_character_email # function

        msg_id = self.dm.post_message(email("guy1"), email("guy2"), subject="ssd", body="qsdqsd")

        msg = self.dm.get_dispatched_message_by_id(msg_id)
        self.assertFalse(msg["has_replied"])
        self.assertFalse(msg["has_read"])

        # no strict checks on sender/recipient of original message, when using parent_id feature
        msg_id2 = self.dm.post_message(email("guy2"), email("guy1"), subject="ssd", body="qsdqsd", parent_id=msg_id)
        msg_id3 = self.dm.post_message(email("guy3"), email("guy2"), subject="ssd", body="qsdqsd", parent_id=msg_id)

        msg = self.dm.get_dispatched_message_by_id(msg_id2) # new message isn't impacted by parent_id
        self.assertFalse(msg["has_replied"])
        self.assertFalse(msg["has_read"])

        msg = self.dm.get_dispatched_message_by_id(msg_id) # replied-to message impacted
        self.assertEqual(len(msg["has_replied"]), 2)
        self.assertTrue("guy2" in msg["has_replied"])
        self.assertTrue("guy3" in msg["has_replied"])
        self.assertEqual(len(msg["has_read"]), 0) # read state of parent messages do NOT autochange

        ######

        (tpl_id, tpl) = self.dm.get_messages_templates().items()[0]
        self.assertEqual(tpl["is_used"], False)

        msg_id4 = self.dm.post_message(email("guy3"), email("guy1"), subject="ssd", body="qsdqsd", use_template=tpl_id)

        msg = self.dm.get_dispatched_message_by_id(msg_id4) # new message isn't impacted
        self.assertFalse(msg["has_replied"])
        self.assertFalse(msg["has_read"])

        tpl = self.dm.get_message_template(tpl_id)
        self.assertEqual(tpl["is_used"], True) # template properly marked as used





    @for_core_module(Chatroom)
    def test_chatroom_operations(self):

        self.assertEqual(self.dm.get_chatroom_messages(0), (0, None, []))

        self._set_user(None)
        self.assertRaises(dm_module.UsageError, self.dm.send_chatroom_message, " hello ")

        self._set_user("guy1")
        self.assertRaises(dm_module.UsageError, self.dm.send_chatroom_message, " ")

        self.assertEqual(self.dm.get_chatroom_messages(0), (0, None, []))

        self.dm.send_chatroom_message(u" héllo <tag> ! ")
        self.dm.send_chatroom_message(" re ")

        self._set_user("guy2")
        self.dm.send_chatroom_message("back")

        (slice_end, previous_msg_timestamp, msgs) = self.dm.get_chatroom_messages(0)
        self.assertEqual(slice_end, 3)
        self.assertEqual(previous_msg_timestamp, None)
        self.assertEqual(len(msgs), 3)

        self.assertEqual(sorted(msgs, key=lambda x: x["time"]), msgs)

        data = [(msg["username"], msg["message"]) for msg in msgs]
        self.assertEqual(data, [("guy1", u"héllo &lt;tag&gt; !"), ("guy1", "re"), ("guy2", "back")]) # MESSAGES ARE ESCAPED IN ZODB, for safety

        (slice_end, previous_msg_timestamp, nextmsgs) = self.dm.get_chatroom_messages(3)
        self.assertEqual(slice_end, 3)
        self.assertEqual(previous_msg_timestamp, msgs[-1]["time"])
        self.assertEqual(len(nextmsgs), 0)

        (slice_end, previous_msg_timestamp, renextmsgs) = self.dm.get_chatroom_messages(2)
        self.assertEqual(slice_end, 3)
        self.assertEqual(previous_msg_timestamp, msgs[-2]["time"])
        self.assertEqual(len(renextmsgs), 1)
        data = [(msg["username"], msg["message"]) for msg in renextmsgs]
        self.assertEqual(data, [("guy2", "back")])



    def test_external_contacts(self):

        master_contacts = set(self.dm.get_user_contacts(self.dm.master_login))

        char_emails = set(self.dm.get_character_emails())
        assert master_contacts & char_emails == char_emails # all chars are in
        assert len(master_contacts) > len(char_emails) + 4
        assert "judicators2@acharis.com" in master_contacts

        emails = set(self.dm.get_user_contacts("guy2"))
        assert self.dm.get_character_email("guy2") in emails # self-emailing OK
        assert "guy3@pangea.com" in emails
        assert "judicators2@acharis.com" in emails
        emails = self.dm.get_character_external_contacts("guy2")
        assert "guy3@pangea.com" not in emails
        assert "judicators2@acharis.com" in emails

        emails = self.dm.get_user_contacts("guy3")
        self.assertEqual(len(emails), len(self.dm.get_character_usernames()), emails)
        emails = self.dm.get_character_external_contacts("guy3")
        self.assertEqual(len(emails), 0, emails)


    @for_core_module(TextMessagingCore)
    def test_globally_registered_contacts(self):

        contact1 = "SOME_EMAILS"
        contact2 = "phoenix@stash.com"
        contact_bad = "qsd qsdqsd"
        good_content = dict(avatar="qsdqsd", description="here a description", access_tokens=None)

        container = self.dm.global_contacts

        # preexisting, immutable entry
        fixture_key = "everyone@chars.com" # test fixture
        assert fixture_key in container
        assert fixture_key in sorted(container.keys())
        assert fixture_key in container.get_all_data()
        assert sorted(container.keys()) == sorted(container.get_all_data().keys())
        assert fixture_key in [i[0] for i in container.get_all_data(as_sorted_list=True)]

        res = container[fixture_key]
        assert res["immutable"]
        with pytest.raises(UsageError):
            container[fixture_key] = good_content.copy() # already existing
        with pytest.raises(UsageError):
            container[fixture_key] = good_content.copy() # immutable
        with pytest.raises(UsageError):
            del container[fixture_key] # immutable
        assert fixture_key in container


        with pytest.raises(UsageError):
            container[contact_bad] = good_content.copy() # bad key


        # dealing with new entry (mutable)
        for contact in (contact1, contact2):

            # not yet present
            assert contact not in container
            assert contact not in container.get_all_data()
            assert contact not in sorted(container.keys())

            with pytest.raises(UsageError):
                container[contact]
            with pytest.raises(UsageError):
                del container[contact]


            with pytest.raises(UsageError):
                container[contact] = {"avatar": 11} # bad content
            with pytest.raises(UsageError):
                container[contact] = {"description": False} # bad content


            container[contact] = good_content.copy()

            assert contact in container
            res = copy.copy(container[contact])
            assert res["immutable"] == False
            del res["immutable"]
            assert res == good_content

            with pytest.raises(UsageError):
                container[contact] = {"avatar": 11} # bad content
            container[contact] = {"avatar": None, "description": None}

            res = copy.copy(container[contact])
            assert res["immutable"] == False
            del res["immutable"]
            assert res == {"avatar": None, "description": None, "access_tokens": None}

            assert contact in container

            del container[contact]
            with pytest.raises(UsageError):
                del container[contact]
            assert contact not in container

            assert contact not in container.get_all_data()
            with pytest.raises(UsageError):
                container[contact]


            # mutability control
            immutable_entry = "auction-list@pangea.com"
            assert immutable_entry in container.get_all_data()
            assert immutable_entry in container.get_all_data(mutability=False)
            assert immutable_entry not in container.get_all_data(mutability=True)
            assert immutable_entry in [k for k, v in container.get_all_data(as_sorted_list=True)]
            assert immutable_entry in [k for k, v in container.get_all_data(as_sorted_list=True, mutability=False)]
            assert immutable_entry not in [k for k, v in container.get_all_data(as_sorted_list=True, mutability=True)]

            mutable_entry = "othercontact@anything.fr"
            assert mutable_entry in container.get_all_data()
            assert mutable_entry in container.get_all_data(mutability=True)
            assert mutable_entry not in container.get_all_data(mutability=False)
            assert mutable_entry in [k for k, v in container.get_all_data(as_sorted_list=True)]
            assert mutable_entry not in [k for k, v in container.get_all_data(as_sorted_list=True, mutability=False)]
            assert mutable_entry in [k for k, v in container.get_all_data(as_sorted_list=True, mutability=True)]
            assert mutable_entry not in [k for k, v in container.get_all_data(as_sorted_list=True, mutability=False)]


    '''        
    @for_core_module(TextMessagingCore)
    def __test_globally_registered_contacts_old(self):
        
        contact1 = "ALL_EMAILS"
        contact2 = "phoenix@stash.com"
        contact_bad = "qsd qsdqsd"
        
        res = self.dm.get_globally_registered_contact_info("ALL_CONTACTS") # test fixture
        self.dm.add_globally_registered_contact("ALL_CONTACTS") # no error
        assert self.dm.get_globally_registered_contact_info("ALL_CONTACTS") == res # untouched if existing
        
        with pytest.raises(AssertionError):
            self.dm.add_globally_registered_contact(contact_bad)
        assert not self.dm.is_globally_registered_contact(contact_bad)
        
        for contact in (contact1, contact2):
            
            assert contact not in self.dm.get_globally_registered_contacts()
            with pytest.raises(AbnormalUsageError):
                self.dm.get_globally_registered_contact_info(contact)   
            with pytest.raises(AbnormalUsageError):
                self.dm.remove_globally_registered_contact(contact)   
                                     
            assert not self.dm.is_globally_registered_contact(contact)
            self.dm.add_globally_registered_contact(contact)
            assert self.dm.is_globally_registered_contact(contact)
            self.dm.add_globally_registered_contact(contact)
            assert self.dm.is_globally_registered_contact(contact)
            
            assert self.dm.get_globally_registered_contact_info(contact) is None
            assert contact in self.dm.get_globally_registered_contacts()
            
            self.dm.remove_globally_registered_contact(contact)
            with pytest.raises(AbnormalUsageError):
                self.dm.get_globally_registered_contact_info(contact)  
            with pytest.raises(AbnormalUsageError):
                self.dm.remove_globally_registered_contact(contact)          
            assert not self.dm.is_globally_registered_contact(contact)
            assert contact not in self.dm.get_globally_registered_contacts()
    '''

    @for_core_module(TextMessagingForCharacters)
    def test_messaging_utilities(self):

        input1 = "guy1 , ; ; guy2@acharis.com , master, ; everyone@lg-auction.com ,master, stuff@micro.fr"
        input2 = ["everyone@lg-auction.com", "guy1@pangea.com", "guy2@acharis.com", "master@pangea.com", "stuff@micro.fr"]


        sender, recipients = self.dm._normalize_message_addresses("  guy1   ", input1)
        assert sender == "guy1@pangea.com"
        self.assertEqual(len(recipients), len(input2))
        self.assertEqual(set(recipients), set(input2))

        sender, recipients = self.dm._normalize_message_addresses(" gu222@microkosm.com", input2)
        assert sender == "gu222@microkosm.com"
        self.assertEqual(len(recipients), len(input2))
        self.assertEqual(set(recipients), set(input2))

        assert self.dm.get_character_or_none_from_email("guy1@pangea.com") == "guy1"
        assert self.dm.get_character_or_none_from_email("guy1@wrongdomain.com") is None
        assert self.dm.get_character_or_none_from_email("master@pangea.com") is None


        sample = u""" Hello hélloaaxsjjs@gmaïl.fr. please write to hérbèrt@hélénia."""
        res = _generate_messaging_links(sample, self.dm)

        # the full email is well linked, not the incomplete one
        assert res == u' Hello <a href="/TeStiNg/messages/compose/?recipient=h%C3%A9lloaaxsjjs%40gma%C3%AFl.fr">h\xe9lloaaxsjjs@gma\xefl.fr</a>. please write to h\xe9rb\xe8rt@h\xe9l\xe9nia.'


        assert self.dm.get_contacts_display_properties([]) == []
        res = self.dm.get_contacts_display_properties(["guy1@pangea.com", "judicators@acharis.com", "unknown@mydomain.com"])
        #print(">>", res)
        assert res == [{'description': 'This is guy1', 'avatar': 'guy1.png', 'address': u'guy1@pangea.com'},
                       {'description': 'the terrible judicators', 'avatar': 'here.jpg', 'address': u'judicators@acharis.com'},
                       {'description': u'Unidentified contact', 'avatar': 'defaultavatar.jpg', 'address': u'unknown@mydomain.com'}]


    def test_mailing_list_special_case(self):

        ml = self.dm.get_global_parameter("all_characters_mailing_list")

        self.dm.post_message("guy2@pangea.com",
                             recipient_emails=["secret-services@masslavia.com", "guy1@pangea.com", ml],
                             subject="subj", body="qsdqsd") # this works too !

        msg = self.dm.get_all_dispatched_messages()[-1]

        assert msg["subject"] == "subj"
        assert msg["visible_by"] == {'guy3': 'recipient',
                                     'guy4': 'recipient',
                                     'master': 'recipient',
                                     'guy2': 'sender', # well set
                                     'guy1': 'recipient'}

        self.dm.post_message("secret-services@masslavia.com",
                             recipient_emails=["guy1@pangea.com", ml],
                             subject="subj2", body="qsdqsd") # this works too !

        msg = self.dm.get_all_dispatched_messages()[-1]

        assert msg["subject"] == "subj2"
        assert msg["visible_by"] == {'guy3': 'recipient',
                                     'guy4': 'recipient',
                                     'master': 'sender',
                                     'guy2': 'recipient',
                                     'guy1': 'recipient'}



    def test_text_messaging_workflow(self):

        self._reset_messages()

        email = self.dm.get_character_email # function

        MASTER = self.dm.get_global_parameter("master_login")

        self.assertEqual(email("guy3"), "guy3@pangea.com")
        with pytest.raises(AssertionError):
            email("master") # not OK with get_character_email!


        record1 = {
            "sender_email": "guy2@pangea.com",
            "recipient_emails": ["guy3@pangea.com"],
            "subject": "hello everybody 1",
            "body": "Here is the body of this message lalalal...",
            "date_or_delay_mn":-1
        }

        record2 = {
            "sender_email": "guy4@pangea.com",
            "recipient_emails": ["secret-services@masslavia.com", "guy2@pangea.com"], # guy2 will both wiretap and receive here
            "subject": "hello everybody 2",
            "body": "Here is the body of this message lililili...",
            "attachment": "http://yowdlayhio",
            "date_or_delay_mn": 0
        }

        record3 = {
            "sender_email": "guy1@pangea.com",
            "recipient_emails": ["guy3@pangea.com"],
            "subject": "hello everybody 3",
            "body": "Here is the body of this message lulululu...",
            "date_or_delay_mn": None
            # "origin": "dummy-msg-id"  # shouldn't raise error - the problem is just logged
        }

        record4 = {
            "sender_email": "dummy-robot@masslavia.com",
            "recipient_emails": ["guy2@pangea.com"],
            "subject": "hello everybody 4",
            "body": "Here is the body of this message lililili...",
            }

        self.dm.post_message("guy1@masslavia.com", # NOT recognised as guy1, because wrong domain
                             "netsdfworkerds@masslavia.com", subject="ssd", body="qsdqsd") # this works too !

        self.assertEqual(len(self.dm.get_user_related_messages(self.dm.master_login)), 1)
        self.dm.get_user_related_messages(self.dm.master_login)[0]["has_read"] = utilities.PersistentList(
            self.dm.get_character_usernames() + [self.dm.get_global_parameter("master_login")]) # we hack this message not to break following assertions

        self.dm.post_message(**record1)
        time.sleep(0.2)

        self.dm.set_wiretapping_targets("guy4", ["guy4"]) # stupid but possible, and harmless actually

        self.dm.set_wiretapping_targets("guy1", ["guy2"])
        self.dm.set_wiretapping_targets("guy2", ["guy4"])

        self.dm.set_wiretapping_targets("guy3", ["guy1"]) # USELESS wiretapping, thanks to SSL/TLS
        self.dm.set_confidentiality_protection_status("guy3", True)

        self.dm.post_message(**record2)
        time.sleep(0.2)
        self.dm.post_message(**record3)
        time.sleep(0.2)
        self.dm.post_message(**record4)
        time.sleep(0.2)
        self.dm.post_message(**record1) # this message will get back to the 2nd place of list !

        print ("@>@>@>@>", self.dm.get_all_dispatched_messages())
        self.assertEqual(self.dm.get_unread_messages_count("guy3"), 3)

        self.assertEqual(self.dm.get_unread_messages_count(self.dm.get_global_parameter("master_login")), 2)

        self.assertEqual(len(self.dm.get_all_dispatched_messages()), 6)

        res = self.dm.get_user_related_messages(self.dm.master_login)
        #pprint.pprint(res)
        self.assertEqual(len(res), 3) # secret services masslavia + wrong newtorker email address + dummy-robot

        expected_notifications = {'guy2': "new_messages_2", 'guy3': "new_messages_1", 'guy1': 'info_spots_1'} # guy1 because of wiretapping, not guy4 because was only a sender
        self.assertEqual(self.dm.get_pending_new_message_notifications(), expected_notifications)
        self.assertEqual(self.dm.get_pending_new_message_notifications(), expected_notifications) # no disappearance

        self.assertTrue(self.dm.has_new_message_notification("guy3"))
        self.assertEqual(len(self.dm.pop_received_messages("guy3")), 3)
        self.assertFalse(self.dm.has_new_message_notification("guy3"))

        # here we can't do check messages of secret-services@masslavia.com since it's not a normal character

        self.assertTrue(self.dm.has_new_message_notification("guy2"))
        self.assertEqual(len(self.dm.get_received_messages("guy2")), 2)
        assert not self.dm.get_intercepted_messages("guy2") # wiretapping is overridden by other visibility reasons

        self.assertTrue(self.dm.has_new_message_notification("guy2"))
        self.dm.set_new_message_notification(utilities.PersistentList(["guy1", "guy2"]), new_status=False)
        self.assertFalse(self.dm.has_new_message_notification("guy1"))
        self.assertFalse(self.dm.has_new_message_notification("guy2"))

        self.assertEqual(self.dm.get_pending_new_message_notifications(), {}) # all have been reset

        self.assertEqual(len(self.dm.get_received_messages("guy1")), 0)

        self.assertEqual(len(self.dm.get_sent_messages("guy2")), 2)
        self.assertEqual(len(self.dm.get_sent_messages("guy1")), 1)
        self.assertEqual(len(self.dm.get_sent_messages("guy3")), 0)

        assert not self.dm.get_intercepted_messages("guy3") # ineffective wiretapping

        res = self.dm.get_intercepted_messages("guy1")
        self.assertEqual(len(res), 3) # wiretapping of user as sender AND recipient
        self.assertEqual(set([msg["subject"] for msg in res]), set(["hello everybody 1", "hello everybody 2", "hello everybody 4"]))
        assert all([msg["visible_by"]["guy1"] == VISIBILITY_REASONS.interceptor for msg in res])

        res = self.dm.get_intercepted_messages(self.dm.master_login)
        self.assertEqual(len(res), 0)

        # game master doesn't need these...
        #self.assertEqual(set([msg["subject"] for msg in res]), set(["hello everybody 1", "hello everybody 2", "hello everybody 4"]))
        #assert all([msg["intercepted_by"] for msg in res])
        # NO - we dont notify interceptions - self.assertTrue(self.dm.get_global_parameter("message_intercepted_audio_id") in self.dm.get_all_next_audio_messages(), self.dm.get_all_next_audio_messages())

        # msg has_read state changes
        msg_id1 = self.dm.get_all_dispatched_messages()[0]["id"] # sent to guy3
        msg_id2 = self.dm.get_all_dispatched_messages()[3]["id"] # sent to external contact

        """ # NO PROBLEM with wrong msg owner
        self.assertRaises(Exception, self.dm.set_message_read_state, MASTER, msg_id1, True)
        self.assertRaises(Exception, self.dm.set_message_read_state, "guy2", msg_id1, True)
        self.assertRaises(Exception, self.dm.set_message_read_state, "guy1", msg_id2, True)
        """

        # wrong msg id
        self.assertRaises(Exception, self.dm.set_message_read_state, "dummyid", False)


        # self.assertEqual(self.dm.get_all_dispatched_messages()[0]["no_reply"], False)
        # self.assertEqual(self.dm.get_all_dispatched_messages()[4]["no_reply"], True)# msg from robot

        self.assertEqual(self.dm.get_all_dispatched_messages()[0]["is_certified"], False)
        self.assertFalse(self.dm.get_all_dispatched_messages()[0]["has_read"])
        self.dm.set_message_read_state("guy3", msg_id1, True)
        self.dm.set_message_read_state("guy2", msg_id1, True)

        self.assertEqual(len(self.dm.get_all_dispatched_messages()[0]["has_read"]), 2)
        self.assertTrue("guy2" in self.dm.get_all_dispatched_messages()[0]["has_read"])
        self.assertTrue("guy3" in self.dm.get_all_dispatched_messages()[0]["has_read"])

        self.assertEqual(self.dm.get_unread_messages_count("guy3"), 2)
        self.dm.set_message_read_state("guy3", msg_id1, False)
        self.assertEqual(self.dm.get_all_dispatched_messages()[0]["has_read"], ["guy2"])
        self.assertEqual(self.dm.get_unread_messages_count("guy3"), 3)

        self.assertFalse(self.dm.get_all_dispatched_messages()[3]["has_read"])
        self.dm.set_message_read_state(MASTER, msg_id2, True)
        self.assertTrue(MASTER in self.dm.get_all_dispatched_messages()[3]["has_read"])
        self.assertEqual(self.dm.get_unread_messages_count(self.dm.get_global_parameter("master_login")), 1)
        self.dm.set_message_read_state(MASTER, msg_id2, False)
        self.assertFalse(self.dm.get_all_dispatched_messages()[3]["has_read"])
        self.assertEqual(self.dm.get_unread_messages_count(self.dm.get_global_parameter("master_login")), 2)



    def test_messaging_address_restrictions(self):

        target = "judicators@acharis.com"
        assert self.dm.global_contacts[target]["access_tokens"] == ["guy1", "guy2"]

        if random.choice((True, False)):
            self._set_user("guy1") # WITHOUT IMPACT HERE

        self.dm.post_message("guy1@pangea.com", [target], "hhh", "hello") # allowed
        self.dm.post_message("othercontact@anything.fr", [target], "hhh", "hello") # allowed
        self.dm.post_message(target, [target], "hhh", "hello") # allowed

        with pytest.raises(UsageError):
            self.dm.post_message("guy3@pangea.com", [target], "hhaah", "hssello") # NOT allowed, because character AND not in access tokens



    def test_wiretapping_methods(self):


        my_user1 = "guy2"
        my_user2 = "guy3"
        my_user3 = "guy4"
        self._set_user(my_user1)

        # standard target setup

        self.dm.set_wiretapping_targets(my_user1, [my_user2])

        assert self.dm.get_wiretapping_targets(my_user1) == [my_user2]
        assert self.dm.get_wiretapping_targets(my_user2) == []
        assert self.dm.get_wiretapping_targets(my_user3) == []

        assert self.dm.get_listeners_for(my_user1) == []
        assert self.dm.get_listeners_for(my_user2) == [my_user1]
        assert self.dm.get_listeners_for(my_user3) == []

        assert self.dm.determine_effective_wiretapping_traps(my_user1) == [my_user2]
        assert self.dm.determine_effective_wiretapping_traps(my_user2) == []
        assert self.dm.determine_effective_wiretapping_traps(my_user3) == []

        assert self.dm.determine_broken_wiretapping_data(my_user1) == {}
        assert self.dm.determine_broken_wiretapping_data(my_user2) == {}
        assert self.dm.determine_broken_wiretapping_data(my_user3) == {}


        # SSL/TLS protection enabled

        self.dm.set_wiretapping_targets(my_user2, [my_user1])  # back link

        assert not self.dm.get_confidentiality_protection_status(my_user1)
        assert not self.dm.get_confidentiality_protection_status(my_user2)

        start = datetime.utcnow()
        self.dm.set_confidentiality_protection_status(my_user1, has_confidentiality=True) # my_user1 is PROTECTED against interceptions!!
        end = datetime.utcnow()

        activation_date = self.dm.get_confidentiality_protection_status(my_user1)
        assert activation_date and (start <= activation_date <= end)
        assert not self.dm.get_confidentiality_protection_status(my_user2)

        assert self.dm.get_wiretapping_targets(my_user1) == [my_user2]
        assert self.dm.get_wiretapping_targets(my_user2) == [my_user1] # well listed, even if ineffective
        assert self.dm.get_wiretapping_targets(my_user3) == []

        assert self.dm.get_listeners_for(my_user1) == [my_user2] # well listed, even if ineffective
        assert self.dm.get_listeners_for(my_user2) == [my_user1]
        assert self.dm.get_listeners_for(my_user3) == []

        assert self.dm.determine_effective_wiretapping_traps(my_user1) == [my_user2]
        assert self.dm.determine_effective_wiretapping_traps(my_user2) == [] # NOT EFFECTIVE
        assert self.dm.determine_effective_wiretapping_traps(my_user3) == []

        assert self.dm.determine_broken_wiretapping_data(my_user1) == {}
        assert self.dm.determine_broken_wiretapping_data(my_user2) == {my_user1: activation_date}
        assert self.dm.determine_broken_wiretapping_data(my_user3) == {}


        # SSL/TLS protection disabled

        self.dm.set_confidentiality_protection_status(has_confidentiality=False) # fallback to current user

        assert not self.dm.get_confidentiality_protection_status(my_user1)
        assert not self.dm.get_confidentiality_protection_status(my_user2)

        assert self.dm.determine_effective_wiretapping_traps(my_user1) == [my_user2]
        assert self.dm.determine_effective_wiretapping_traps(my_user2) == [my_user1]
        assert self.dm.determine_effective_wiretapping_traps(my_user3) == []

        assert self.dm.determine_broken_wiretapping_data(my_user1) == {}
        assert self.dm.determine_broken_wiretapping_data(my_user2) == {}
        assert self.dm.determine_broken_wiretapping_data(my_user3) == {}



    def test_audio_messages_management(self):
        self._reset_messages()

        email = self.dm.get_character_email # function

        self.assertRaises(dm_module.UsageError, self.dm.check_radio_frequency, "dummyfrequency")
        self.assertEqual(self.dm.check_radio_frequency(self.dm.get_global_parameter("pangea_radio_frequency")), None) # no exception nor return value

        self.dm.set_radio_state(is_on=True)
        self.assertEqual(self.dm.get_global_parameter("radio_is_on"), True)
        self.dm.set_radio_state(is_on=False)
        self.assertEqual(self.dm.get_global_parameter("radio_is_on"), False)
        self.dm.set_radio_state(is_on=True)
        self.assertEqual(self.dm.get_global_parameter("radio_is_on"), True)

        record1 = {
            "sender_email": email("guy2"),
            "recipient_emails": [email("guy3")],
            "subject": "hello everybody 1",
            "body": "Here is the body of this message lalalal...",
            "date_or_delay_mn":-1
        }

        self.dm.post_message(**record1)

        res = self.dm.get_pending_new_message_notifications()
        self.assertEqual(len(res), 1)
        (username, audio_id) = res.items()[0]
        self.assertEqual(username, "guy3")

        properties = self.dm.get_audio_message_properties(audio_id)
        self.assertEqual(set(properties.keys()), set(["title", "text", "file", "url", "immutable"]))

        # self.assertEqual(properties["new_messages_notification_for_user"], "guy3")
        # self.assertEqual(self.dm.get_audio_message_properties("request_for_report_teldorium")["new_messages_notification_for_user"], None)

        self.assertEqual(len(self.dm.get_all_next_audio_messages()), 0)

        assert self.dm.has_read_current_playlist("guy4") # empty playlist ALWAYS read
        assert self.dm.has_read_current_playlist("guy3")

        self.dm.add_radio_message(audio_id)
        self.assertEqual(self.dm.get_next_audio_message(), audio_id)
        self.assertEqual(self.dm.get_next_audio_message(), audio_id) # no disappearance
        assert not self.dm.has_read_current_playlist("guy4")

        assert not self.dm.has_read_current_playlist("guy4") # RESET
        self.dm.mark_current_playlist_read("guy4")
        assert self.dm.has_read_current_playlist("guy4")
        assert not self.dm.has_read_current_playlist("guy3")

        self.assertEqual(len(self.dm.get_all_next_audio_messages()), 1)

        self.dm.reset_audio_messages()
        self.assertEqual(self.dm.get_next_audio_message(), None)

        self.assertEqual(len(self.dm.get_all_next_audio_messages()), 0)

        audio_id_bis = self.dm.get_character_properties("guy2")["new_messages_notification"]
        audio_id_ter = self.dm.get_character_properties("guy1")["new_messages_notification"]

        self.assertRaises(dm_module.UsageError, self.dm.add_radio_message, "bad_audio_id")
        self.dm.add_radio_message(audio_id)
        self.dm.add_radio_message(audio_id) # double adding == NO OP
        self.dm.add_radio_message(audio_id_bis)
        self.dm.add_radio_message(audio_id_ter)

        self.assertEqual(len(self.dm.get_all_next_audio_messages()), 3)
        assert self.dm.get_all_next_audio_messages() == [audio_id, audio_id_bis, audio_id_ter]

        self.assertEqual(self.dm.get_next_audio_message(), audio_id)

        self.dm.notify_audio_message_termination("bad_audio_id") # no error, we just ignore it

        self.dm.notify_audio_message_termination(audio_id_ter) # removing trailing one works

        self.dm.notify_audio_message_termination(audio_id)

        self.assertEqual(self.dm.get_global_parameter("radio_is_on"), True)

        self.assertEqual(self.dm.get_next_audio_message(), audio_id_bis)
        self.dm.notify_audio_message_termination(audio_id_bis)

        self.assertEqual(self.dm.get_global_parameter("radio_is_on"), False) # auto extinction of radio

        self.assertEqual(self.dm.get_next_audio_message(), None)
        self.assertEqual(len(self.dm.get_all_next_audio_messages()), 0)

        self.dm.set_radio_messages([audio_id_bis, audio_id_ter])

        self.dm.mark_current_playlist_read("guy2")
        assert self.dm.has_read_current_playlist("guy2")
        assert not self.dm.has_read_current_playlist("guy3")

        self.dm.set_radio_messages([audio_id_bis, audio_id_ter]) # UNCHANGED

        assert self.dm.has_read_current_playlist("guy2") # UNCHANGED
        assert not self.dm.has_read_current_playlist("guy3")

        self.dm.add_radio_message(audio_id_ter) # UNCHANGED

        assert self.dm.has_read_current_playlist("guy2") # UNCHANGED
        assert not self.dm.has_read_current_playlist("guy3")

        self.dm.set_radio_messages([audio_id_bis, audio_id_ter, audio_id_ter]) # finally changed
        assert self.dm.get_all_next_audio_messages() == [audio_id_bis, audio_id_ter, audio_id_ter]
        self.assertEqual(self.dm.get_next_audio_message(), audio_id_bis)

        assert not self.dm.has_read_current_playlist("guy2") # RESET
        assert not self.dm.has_read_current_playlist("guy3")


    def test_delayed_message_processing_and_message_deletion(self):

        WANTED_FACTOR = 2 # we only double durations below
        params = self.dm.get_global_parameters()
        assert params["game_theoretical_length_days"]
        params["game_theoretical_length_days"] = WANTED_FACTOR


        self._reset_messages()

        email = self.dm.get_character_email # function

        # delayed message sending

        self.dm.post_message(email("guy3"), email("guy2"), "yowh1", "qhsdhqsdh", attachment=None, date_or_delay_mn=0.03 / WANTED_FACTOR)
        self.assertEqual(len(self.dm.get_all_dispatched_messages()), 0)
        queued_msgs = self.dm.get_all_queued_messages()
        self.assertEqual(len(queued_msgs), 1)
        # print datetime.utcnow(), " << ", queued_msgs[0]["sent_at"]
        self.assertTrue(datetime.utcnow() < queued_msgs[0]["sent_at"] < datetime.utcnow() + timedelta(minutes=0.22))

        self.dm.post_message(email("guy3"), email("guy2"), "yowh2", "qhsdhqsdh", attachment=None, date_or_delay_mn=(0.04 / WANTED_FACTOR, 0.05 / WANTED_FACTOR)) # 3s delay range
        self.assertEqual(len(self.dm.get_all_dispatched_messages()), 0)
        queued_msgs = self.dm.get_all_queued_messages()
        self.assertEqual(len(queued_msgs), 2)
        self.assertEqual(queued_msgs[1]["subject"], "yowh2", queued_msgs)
        # print datetime.utcnow(), " >> ", queued_msgs[1]["sent_at"]
        self.assertTrue(datetime.utcnow() < queued_msgs[1]["sent_at"] < datetime.utcnow() + timedelta(minutes=0.06))

        # delayed message processing

        self.dm.post_message(email("guy3"), email("guy2"), "yowh3", "qhsdhqsdh", attachment=None, date_or_delay_mn=0.01 / WANTED_FACTOR) # 0.6s
        self.assertEqual(len(self.dm.get_all_queued_messages()), 3)
        self.assertEqual(len(self.dm.get_all_dispatched_messages()), 0)
        res = self.dm.process_periodic_tasks()
        self.assertEqual(res["messages_dispatched"], 0)
        self.assertEqual(res["actions_executed"], 0)
        self.assertEqual(len(self.dm.get_all_dispatched_messages()), 0)

        time.sleep(0.8) # one message OK

        res = self.dm.process_periodic_tasks()
        # print self.dm.get_all_dispatched_messages(), datetime.utcnow()
        self.assertEqual(res["messages_dispatched"], 1)
        self.assertEqual(res["actions_executed"], 0)
        self.assertEqual(len(self.dm.get_all_dispatched_messages()), 1)
        # print(">>>>>>>>>>>>>>>>>>>>>>##", self.dm.get_all_queued_messages())
        self.assertEqual(len(self.dm.get_all_queued_messages()), 2)

        time.sleep(2.5) # last messages OK

        res = self.dm.process_periodic_tasks()
        self.assertEqual(res["messages_dispatched"], 2)
        self.assertEqual(res["actions_executed"], 0)
        self.assertEqual(len(self.dm.get_all_dispatched_messages()), 3)
        self.assertEqual(len(self.dm.get_all_queued_messages()), 0)

        # due to the strength of coherency checks, it's about impossible to enforce a sending here here...
        self.assertEqual(self.dm.get_event_count("DELAYED_MESSAGE_ERROR"), 0)


        # forced sending of queued messages
        myid1 = self.dm.post_message(email("guy3"), email("guy2"), "yowh2", "qhsdhqsdh", attachment=None, date_or_delay_mn=(1.0 / WANTED_FACTOR, 2.0 / WANTED_FACTOR)) # 3s delay range
        myid2 = self.dm.post_message(email("guy3"), email("guy2"), "yowh2", "qhsdhqsdh", attachment=None, date_or_delay_mn=(1.0 / WANTED_FACTOR, 2.0 / WANTED_FACTOR)) # 3s delay range
        assert myid1 != myid2
        self.assertEqual(len(self.dm.get_all_queued_messages()), 2)

        self.assertFalse(self.dm.force_message_sending("dummyid"))
        self.assertTrue(self.dm.force_message_sending(myid1))
        self.assertEqual(len(self.dm.get_all_queued_messages()), 1)
        self.assertFalse(self.dm.force_message_sending(myid1)) # already sent now
        self.assertEqual(self.dm.get_all_queued_messages()[0]["id"], myid2)
        self.assertTrue(self.dm.get_dispatched_message_by_id(myid1))


        # message deletion #
        assert not self.dm.permanently_delete_message("badid")

        assert self.dm.permanently_delete_message(myid1) # DISPATCHED MESSAGE DELETED
        assert not self.dm.permanently_delete_message(myid1)
        with pytest.raises(UsageError):
            self.dm.get_dispatched_message_by_id(myid1) # already deleted

        assert self.dm.permanently_delete_message(myid2) # QUEUED MESSAGE DELETED
        assert not self.dm.permanently_delete_message(myid2)
        assert not self.dm.get_all_queued_messages()



    def test_delayed_action_processing(self):

        WANTED_FACTOR = 2 # we only double durations below
        params = self.dm.get_global_parameters()
        assert params["game_theoretical_length_days"]
        params["game_theoretical_length_days"] = WANTED_FACTOR


        def _dm_delayed_action(arg1):
            self.dm.data["global_parameters"]["stuff"] = 23
            self.dm.commit()
        self.dm._dm_delayed_action = _dm_delayed_action # now an attribute of that speific instance, not class!

        self.dm.schedule_delayed_action(0.01 / WANTED_FACTOR, dummyfunc, 12, item=24)
        self.dm.schedule_delayed_action((0.04 / WANTED_FACTOR, 0.05 / WANTED_FACTOR), dummyfunc) # will raise error
        self.dm.schedule_delayed_action((0.035 / WANTED_FACTOR, 0.05 / WANTED_FACTOR), "_dm_delayed_action", "hello")

        res = self.dm.process_periodic_tasks()
        self.assertEqual(res["actions_executed"], 0)

        time.sleep(0.7)

        res = self.dm.process_periodic_tasks()
        self.assertEqual(res["actions_executed"], 1)

        self.assertEqual(self.dm.get_event_count("DELAYED_ACTION_ERROR"), 0)
        assert self.dm.data["global_parameters"].get("stuff") is None

        time.sleep(2.5)

        res = self.dm.process_periodic_tasks()
        self.assertEqual(res["actions_executed"], 2)

        self.assertEqual(len(self.dm.data["scheduled_actions"]), 0)

        self.assertEqual(self.dm.get_event_count("DELAYED_ACTION_ERROR"), 1) # error raised but swallowed
        assert self.dm.data["global_parameters"]["stuff"] == 23



    @for_core_module(PlayerAuthentication)
    def test_standard_user_authentication(self):
        """
        Here we use frontend methods from authentication.py instead of
        directly datamanager methods.
        """
        self._reset_django_db()

        OTHER_SESSION_TICKET_KEY = SESSION_TICKET_KEY_TEMPLATE % "my_other_test_game_id"

        home_url = reverse(views.homepage, kwargs={"game_instance_id": TEST_GAME_INSTANCE_ID})

        master_login = self.dm.get_global_parameter("master_login")
        master_password = self.dm.get_global_parameter("master_password")
        player_login = "guy1"
        player_password = "elixir"
        anonymous_login = self.dm.get_global_parameter("anonymous_login")


        # build complete request
        request = self.factory.post(home_url)
        request.datamanager = self.dm

        # we let different states of the session ticket be there, at the beginning
        if random.choice((0, 1)):
            request.session[SESSION_TICKET_KEY] = random.choice((None, {}))

        # anonymous case
        assert request.datamanager.user.username == anonymous_login
        assert not self.dm.get_impersonation_targets(anonymous_login)


        def _standard_authenticated_checks():

            # we set a ticket for another game instance, different
            other_session_ticket = random.choice((None, True, {'a': 'b'}, [1, 2]))
            request.session[OTHER_SESSION_TICKET_KEY] = copy.copy(other_session_ticket)


            original_ticket = request.session[SESSION_TICKET_KEY].copy()
            original_username = request.datamanager.user.username

            assert request.datamanager == self.dm
            self._set_user(None)
            assert request.datamanager.user.username == anonymous_login
            assert request.datamanager.user.real_username == anonymous_login
            assert request.datamanager.user.has_write_access
            assert not request.datamanager.user.is_impersonation
            assert not request.datamanager.user.impersonation_target
            assert not request.datamanager.user.impersonation_writability
            assert not request.datamanager.user.is_superuser

            res = try_authenticating_with_session(request)
            assert res is None

            assert request.session[SESSION_TICKET_KEY] == original_ticket
            assert request.datamanager.user.username == original_username
            assert request.datamanager.user.real_username == original_username
            assert request.datamanager.user.has_write_access
            assert not request.datamanager.user.is_impersonation
            assert not request.datamanager.user.impersonation_target
            assert not request.datamanager.user.impersonation_writability
            assert not request.datamanager.user.is_superuser

            self._set_user(None)

            # failure case: wrong ticket type
            request.session[SESSION_TICKET_KEY] = ["dqsdqs"]
            try_authenticating_with_session(request) # exception gets swallowed
            assert request.session[SESSION_TICKET_KEY] is None

            self._set_user(None)

            # failure case: wrong instance id
            request.session[SESSION_TICKET_KEY] = original_ticket.copy()
            request.session[SESSION_TICKET_KEY]["game_instance_id"] = "qsdjqsidub"
            _temp = request.session[SESSION_TICKET_KEY].copy()
            try_authenticating_with_session(request)
            assert request.session[SESSION_TICKET_KEY] == None # removed

            self._set_user(None)

            request.session[SESSION_TICKET_KEY] = original_ticket.copy()
            request.session[SESSION_TICKET_KEY]["game_username"] = "qsdqsdqsd"
            try_authenticating_with_session(request) # exception gets swallowed
            assert request.session[SESSION_TICKET_KEY] == None # but ticket gets reset

            self._set_user(None)

            request.session[SESSION_TICKET_KEY] = original_ticket.copy()
            try_authenticating_with_session(request)
            assert request.datamanager.user.username == original_username

            logout_session(request)
            assert SESSION_TICKET_KEY not in request.session
            assert request.datamanager.user.username == anonymous_login # reset
            assert request.session[OTHER_SESSION_TICKET_KEY] == other_session_ticket # other session ticket UNTOUCHED by logout

            request.session[SESSION_TICKET_KEY] = original_ticket.copy()
            try_authenticating_with_session(request)
            assert request.datamanager.user.username == original_username

            clear_all_sessions(request) # FULL reset, including django user data
            assert SESSION_TICKET_KEY not in request.session
            assert request.datamanager.user.username == anonymous_login # reset
            assert OTHER_SESSION_TICKET_KEY not in request.session


        # simple player case

        res = try_authenticating_with_credentials(request, player_login, player_password)
        assert res is None # no result expected
        ticket = request.session[SESSION_TICKET_KEY]
        assert ticket == {'game_instance_id': TEST_GAME_INSTANCE_ID, 'impersonation_target': None,
                          'impersonation_writability': None, 'game_username': player_login}

        assert request.datamanager.user.username == player_login
        assert not self.dm.get_impersonation_targets(player_login)

        _standard_authenticated_checks()


        # game master case

        res = try_authenticating_with_credentials(request, master_login, master_password)
        assert res is None # no result expected
        ticket = request.session[SESSION_TICKET_KEY]
        assert ticket == {'game_instance_id': TEST_GAME_INSTANCE_ID, 'impersonation_target': None,
                          'impersonation_writability': None, 'game_username': master_login}

        _standard_authenticated_checks()



    @for_core_module(PlayerAuthentication)
    def test_impersonation_by_superuser(self):

        # TODO check that staff django_user doesn't mess with friendship impersonations either!!!!!!!!

        master_login = self.dm.get_global_parameter("master_login")
        master_password = self.dm.get_global_parameter("master_password")
        player_login = "guy1"
        player_password = "elixir"
        player_login_bis = "guy2"
        anonymous_login = self.dm.get_global_parameter("anonymous_login")


        # use django user, without privileges or inactive #

        now = timezone.now()
        django_user = User(username='fakename', email='my@email.fr',
                      is_staff=False, is_active=True, is_superuser=False,
                      last_login=now, date_joined=now)


        session_ticket = {'game_instance_id': TEST_GAME_INSTANCE_ID, 'impersonation_target': None,
                           'impersonation_writability': None, 'game_username': None}

        for i in range(6):

            if random.choice((True, False)):
                django_user.is_active = True
                django_user.is_staff = django_user.is_superuser = False
            else:
                django_user.is_active = False
                django_user.is_staff = random.choice((True, False))
                if django_user.is_staff:
                    django_user.is_superuser = random.choice((True, False))
                else:
                    django_user.is_superuser = False

            requested_impersonation_target = random.choice((None, master_login, player_login, anonymous_login))
            requested_impersonation_writability = random.choice((True, False, None))
            res = self.dm.authenticate_with_session_data(session_ticket.copy(), # COPY
                                                   requested_impersonation_target=requested_impersonation_target,
                                                   requested_impersonation_writability=requested_impersonation_writability,
                                                   django_user=django_user)
            assert res == {u'game_username': None,
                           u'impersonation_target': None, # we can't impersonate because inactive or not staff user
                           u'impersonation_writability': None, # blocked because non-privileged user
                           u'game_instance_id': TEST_GAME_INSTANCE_ID}
            assert self.dm.user.username == anonymous_login
            assert self.dm.user.has_write_access
            assert not self.dm.user.is_superuser
            assert not self.dm.user.is_impersonation
            assert self.dm.user.real_username == anonymous_login
            assert self.dm.user.has_notifications() == bool(requested_impersonation_target)
            self.dm.user.discard_notifications()

            # ANONYMOUS CASE
            expected_capabilities = dict(display_impersonation_target_shortcut=False,
                                         display_impersonation_writability_shortcut=False,
                                         impersonation_targets=[],
                                         has_writability_control=False,
                                         current_impersonation_target=None,
                                         current_impersonation_writability=False)
            assert self.dm.get_current_user_impersonation_capabilities() == expected_capabilities

            # then we look at impersonation by django super user #

            django_user.is_active = True
            django_user.is_staff = True
            django_user.is_superuser = random.choice((True, False))

            requested_impersonation_target = random.choice((None, master_login, player_login, anonymous_login))
            requested_impersonation_writability = random.choice((True, False, None))
            res = self.dm.authenticate_with_session_data(session_ticket.copy(), # COPY
                                                   requested_impersonation_target=requested_impersonation_target,
                                                   requested_impersonation_writability=requested_impersonation_writability,
                                                   django_user=django_user)
            assert res == {u'game_username': None, # left as None!
                           u'impersonation_target': requested_impersonation_target, # no saving of fallback impersonation into session
                           u'impersonation_writability': requested_impersonation_writability,
                           u'game_instance_id': TEST_GAME_INSTANCE_ID}
            assert self.dm.user.username == requested_impersonation_target if requested_impersonation_target else anonymous_login # AUTO FALLBACK

            _expected_writability = True if not requested_impersonation_target else bool(requested_impersonation_writability)
            assert self.dm.user.has_write_access == _expected_writability
            assert self.dm.user.is_superuser
            assert self.dm.user.is_impersonation == bool(requested_impersonation_target)
            assert self.dm.user.impersonation_target == requested_impersonation_target
            assert self.dm.user.impersonation_writability == bool(requested_impersonation_writability)
            assert self.dm.user.real_username == anonymous_login # LEFT ANONYMOUS, superuser status does it all
            assert not self.dm.user.has_notifications()
            self.dm.user.discard_notifications()

            # SUPERUSER CASE
            expected_capabilities = dict(display_impersonation_target_shortcut=True,
                                         display_impersonation_writability_shortcut=True,
                                        impersonation_targets=self.dm.get_available_logins(),
                                        has_writability_control=True,
                                        current_impersonation_target=requested_impersonation_target,
                                        current_impersonation_writability=bool(requested_impersonation_writability))
            assert self.dm.get_current_user_impersonation_capabilities() == expected_capabilities



    @for_core_module(PlayerAuthentication)
    def test_impersonation_by_master(self):

        # FIXME - test for django super user, for friendship................

        self._reset_django_db()

        master_login = self.dm.get_global_parameter("master_login")
        master_password = self.dm.get_global_parameter("master_password")
        player_login = "guy1"
        player_password = "elixir"
        player_login_bis = "guy2"
        anonymous_login = self.dm.get_global_parameter("anonymous_login")

        if random.choice((True, False)):
            # django superuser has no effect on authentications, as long as a game user is provided
            now = timezone.now()
            django_user = User(username='fakename', email='my@email.fr',
                              is_staff=True, is_active=True, is_superuser=True,
                              last_login=now, date_joined=now)
        else:
            django_user = None

        # build complete request


        # Impersonation control with can_impersonate() - THAT TEST COULD BE MOVED SOEMWHERE ELSE
        assert not self.dm.can_impersonate(master_login, master_login)
        assert self.dm.can_impersonate(master_login, player_login)
        assert self.dm.can_impersonate(master_login, anonymous_login)

        assert not self.dm.can_impersonate(player_login, master_login)
        assert not self.dm.can_impersonate(player_login, player_login)
        assert not self.dm.can_impersonate(player_login, player_login_bis)
        assert not self.dm.can_impersonate(player_login, anonymous_login)

        assert not self.dm.can_impersonate(anonymous_login, master_login)
        assert not self.dm.can_impersonate(anonymous_login, player_login)
        assert not self.dm.can_impersonate(anonymous_login, anonymous_login)


        # Impersonation cases #

        self.dm.user.discard_notifications()

        request = self.request
        try_authenticating_with_credentials(request, master_login, master_password)
        base_session_ticket = request.session[SESSION_TICKET_KEY]
        assert base_session_ticket == {'game_instance_id': TEST_GAME_INSTANCE_ID, 'impersonation_target': None,
                                       'impersonation_writability': None, 'game_username': master_login}
        assert self.dm.user.username == master_login
        assert self.dm.user.has_write_access
        assert not self.dm.user.is_superuser # reserved to staff django users
        assert not self.dm.user.is_impersonation
        assert not self.dm.user.impersonation_target
        assert not self.dm.user.impersonation_writability
        assert self.dm.user.real_username == master_login
        assert not self.dm.user.has_notifications()


        # Impersonate player
        for writability in (None, True, False):

            session_ticket = base_session_ticket.copy()

            res = self.dm.authenticate_with_session_data(session_ticket,
                                                   requested_impersonation_target=player_login,
                                                   requested_impersonation_writability=writability,
                                                   django_user=django_user)
            assert res is session_ticket
            assert session_ticket == {'game_instance_id': TEST_GAME_INSTANCE_ID, 'impersonation_target': player_login,
                                      'impersonation_writability': writability, 'game_username': master_login}

            assert self.dm.user.username == player_login
            assert self.dm.user.has_write_access == bool(writability) # no write access by default, if requested_impersonation_writability is None
            assert not self.dm.user.is_superuser
            assert self.dm.user.is_impersonation
            assert self.dm.user.impersonation_target == player_login
            assert self.dm.user.impersonation_writability == bool(writability)
            assert self.dm.user.real_username == master_login
            assert not self.dm.user.has_notifications()

            # Impersonated player renewed just with ticket
            self._set_user(None)
            assert self.dm.user.username == anonymous_login
            self.dm.authenticate_with_session_data(session_ticket,
                                             requested_impersonation_target=None,
                                             requested_impersonation_writability=None,
                                             django_user=django_user)
            assert session_ticket == {'game_instance_id': TEST_GAME_INSTANCE_ID, 'impersonation_target': player_login,
                                      'impersonation_writability': writability, 'game_username': master_login}

            assert self.dm.user.username == player_login
            assert not self.dm.user.has_notifications()

            # Unexisting impersonation target leads to bad exception (should never happen)
            with pytest.raises(AbnormalUsageError):
                self.dm.authenticate_with_session_data(session_ticket,
                                                 requested_impersonation_target="dsfsdfkjsqodsd",
                                                 requested_impersonation_writability=not writability,
                                                 django_user=django_user)
            # untouched - upper layers must reset that ticket in session
            assert session_ticket == {'game_instance_id': TEST_GAME_INSTANCE_ID, 'impersonation_target': player_login,
                                      'impersonation_writability': writability, 'game_username': master_login}



            # Impersonate anonymous
            self.dm.authenticate_with_session_data(session_ticket,
                                             requested_impersonation_target=anonymous_login,
                                             requested_impersonation_writability=writability,
                                             django_user=django_user)
            assert session_ticket == {'game_instance_id': TEST_GAME_INSTANCE_ID, 'impersonation_target': anonymous_login,
                                      'impersonation_writability': writability, 'game_username': master_login}

            assert self.dm.user.username == anonymous_login
            assert self.dm.user.has_write_access == bool(writability)
            assert not self.dm.user.is_superuser
            assert self.dm.user.is_impersonation
            assert self.dm.user.impersonation_target == anonymous_login
            assert self.dm.user.impersonation_writability == bool(writability)
            assert self.dm.user.real_username == master_login
            assert not self.dm.user.has_notifications()

            # MASTER CASE
            expected_capabilities = dict(display_impersonation_target_shortcut=True,
                                         display_impersonation_writability_shortcut=True,
                                         impersonation_targets=[self.dm.anonymous_login] + self.dm.get_character_usernames(),
                                         has_writability_control=True,
                                         current_impersonation_target=anonymous_login,
                                         current_impersonation_writability=bool(writability))
            assert self.dm.get_current_user_impersonation_capabilities() == expected_capabilities


            # Impersonation stops completely because of unauthorized impersonation attempt
            self.dm.authenticate_with_session_data(session_ticket,
                                             requested_impersonation_target=master_login,
                                             requested_impersonation_writability=writability,
                                             django_user=None) # no django staff user here
            assert session_ticket == {'game_instance_id': TEST_GAME_INSTANCE_ID, 'impersonation_target': None,
                                      'impersonation_writability': None, 'game_username': master_login}
            assert self.dm.user.username == master_login
            assert self.dm.user.has_write_access # always if not impersonation
            assert not self.dm.user.is_superuser
            assert not self.dm.user.is_impersonation
            assert not self.dm.user.impersonation_target
            assert not self.dm.user.impersonation_writability
            assert self.dm.user.real_username == master_login
            assert self.dm.user.has_notifications()
            self.dm.user.discard_notifications()


            # Back as anonymous
            self.dm.authenticate_with_session_data(session_ticket,
                                                     requested_impersonation_target=anonymous_login,
                                                     requested_impersonation_writability=writability,
                                                     django_user=django_user)
            assert session_ticket == {'game_instance_id': TEST_GAME_INSTANCE_ID, 'impersonation_target': anonymous_login,
                                      'impersonation_writability': writability, 'game_username': master_login}

            assert self.dm.user.username == anonymous_login
            assert self.dm.user.has_write_access == bool(writability)
            assert not self.dm.user.is_superuser
            assert self.dm.user.is_impersonation
            assert self.dm.user.impersonation_target == anonymous_login
            assert self.dm.user.impersonation_writability == bool(writability)
            assert self.dm.user.real_username == master_login
            assert not self.dm.user.has_notifications()


            # Standard stopping of impersonation
            self.dm.authenticate_with_session_data(session_ticket,
                                             requested_impersonation_target="",
                                             requested_impersonation_writability=writability,
                                             django_user=django_user)
            assert session_ticket == {'game_instance_id': TEST_GAME_INSTANCE_ID,
                                      'impersonation_target': None,
                                      'impersonation_writability': False, # RESET
                                      'game_username': master_login}

            assert self.dm.user.username == master_login
            assert self.dm.user.has_write_access # always
            assert not self.dm.user.is_superuser
            assert not self.dm.user.is_impersonation
            assert not self.dm.user.impersonation_target
            assert self.dm.user.impersonation_writability == False # RESET
            assert self.dm.user.real_username == master_login
            assert not self.dm.user.has_notifications() # IMPORTANT - no error message



    @for_core_module(PlayerAuthentication)
    def test_impersonation_by_character(self):

        django_user = None
        if random.choice((True, False)):
            now = timezone.now()
            django_user = User(username='fakename', email='my@email.fr',
                          is_staff=random.choice((True, False)), is_active=random.choice((True, False)),
                          is_superuser=random.choice((True, False)), last_login=now, date_joined=now)

        player_name = "guy1"
        other_player = "guy2"
        session_ticket = {'game_instance_id': TEST_GAME_INSTANCE_ID, 'impersonation_target': None,
                            'impersonation_writability': None, 'game_username': player_name}

        if random.choice((True, False)):
            if random.choice((True, False)):
                self.dm.propose_friendship(player_name, other_player)
            else:
                self.dm.propose_friendship(other_player, player_name)

        self.dm.authenticate_with_session_data(session_ticket,
                                                 requested_impersonation_target=other_player,
                                                 requested_impersonation_writability=random.choice((True, False)),
                                                 django_user=django_user)
        session_ticket = {'game_instance_id': TEST_GAME_INSTANCE_ID, 'impersonation_target': None,
                            'impersonation_writability': None, 'game_username': player_name} # writability change rejected as well
        assert self.dm.username == player_name # no impersonation, even if friendship proposals
        assert self.dm.user.has_write_access
        assert not self.dm.user.is_superuser
        assert not self.dm.user.is_impersonation
        assert not self.dm.user.impersonation_target
        assert not self.dm.user.impersonation_writability
        assert self.dm.user.real_username == player_name

        expected_capabilities = dict(display_impersonation_target_shortcut=False,
                                     display_impersonation_writability_shortcut=False,
                                    impersonation_targets=[], # needs frienships
                                    has_writability_control=False,
                                    current_impersonation_target=None,
                                    current_impersonation_writability=False)
        assert self.dm.get_current_user_impersonation_capabilities() == expected_capabilities



        # we finish the friendship
        try:
            self.dm.propose_friendship(player_name, other_player)
        except AbnormalUsageError:
            pass
        try:
            self.dm.propose_friendship(other_player, player_name)
        except AbnormalUsageError:
            pass
        assert self.dm.are_friends(player_name, other_player)

        self.dm.authenticate_with_session_data(session_ticket,
                                                 requested_impersonation_target=other_player,
                                                 requested_impersonation_writability=random.choice((True, False)),
                                                 django_user=django_user)
        session_ticket = {'game_instance_id': TEST_GAME_INSTANCE_ID, 'impersonation_target': None,
                            'impersonation_writability': None, 'game_username': player_name} # writability change rejected in ANY CASE
        assert self.dm.username == other_player # no impersonation, even if friendship proposals
        assert not self.dm.user.has_write_access
        assert not self.dm.user.is_superuser
        assert self.dm.user.is_impersonation
        assert self.dm.user.impersonation_target == other_player
        assert not self.dm.user.impersonation_writability
        assert self.dm.user.real_username == player_name # well kept


        expected_capabilities = dict(display_impersonation_target_shortcut=True, # NOW we display shortcut
                                     display_impersonation_writability_shortcut=False, # NEVER
                                    impersonation_targets=[other_player],
                                    has_writability_control=False,
                                    current_impersonation_target=other_player,
                                    current_impersonation_writability=False)
        assert self.dm.get_current_user_impersonation_capabilities() == expected_capabilities






    @for_core_module(PlayerAuthentication)
    def test_password_operations(self):
        self._reset_messages()

        # "secret question" system

        with raises_with_content(NormalUsageError, "master"):
            self.dm.get_secret_question(self.dm.get_global_parameter("master_login"))
        with raises_with_content(NormalUsageError, "master"):
            self.dm.process_secret_answer_attempt(self.dm.get_global_parameter("master_login"), "FluFFy", "guy3@pangea.com")

        with raises_with_content(NormalUsageError, "invalid"):
            self.dm.get_secret_question("sdqqsd")
        with raises_with_content(NormalUsageError, "invalid"):
            self.dm.process_secret_answer_attempt("sdqqsd", "FluFFy", "guy3@pangea.com")

        with raises_with_content(NormalUsageError, "no secret question"):
            self.dm.get_secret_question("guy1")
        with raises_with_content(NormalUsageError, "no secret question"):
            self.dm.process_secret_answer_attempt("guy1", "FluFFy", "guy3@pangea.com")

        res = self.dm.get_secret_question("guy3")
        self.assertTrue("pet" in res)

        self.assertEqual(len(self.dm.get_all_queued_messages()), 0)
        res = self.dm.process_secret_answer_attempt("guy3", "FluFFy", "guy3@pangea.com")
        self.assertEqual(res, "awesome") # password

        msgs = self.dm.get_all_queued_messages()
        self.assertEqual(len(msgs), 1)
        msg = msgs[0]
        self.assertTrue("password" in msg["body"].lower())

        self.assertRaises(dm_module.UsageError, self.dm.process_secret_answer_attempt, "badusername", "badanswer", "guy3@sciences.com")
        self.assertRaises(dm_module.UsageError, self.dm.process_secret_answer_attempt, "guy3", "badanswer", "guy3@sciences.com")
        self.assertRaises(dm_module.UsageError, self.dm.process_secret_answer_attempt, "guy3", "MiLoU", "bademail@sciences.com")
        self.assertEqual(len(self.dm.get_all_queued_messages()), 1) # untouched


        # password change

        with pytest.raises(NormalUsageError):
            self.dm.process_password_change_attempt("guy1", "badpwd", "newpwd")
        with pytest.raises(AbnormalUsageError):
            self.dm.process_password_change_attempt("guy1", "badpwd", "new pwd") # wrong new pwd
        with pytest.raises(AbnormalUsageError):
            self.dm.process_password_change_attempt("guy1", "elixir", "newpwd\n") # wrong new pwd
        with pytest.raises(AbnormalUsageError):
            self.dm.process_password_change_attempt("guy1", "elixir", "") # wrong new pwd
        with pytest.raises(AbnormalUsageError):
            self.dm.process_password_change_attempt("guy1", "elixir", None) # wrong new pwd


        self.dm.process_password_change_attempt("guy1", "elixir", "newpwd")
        with pytest.raises(NormalUsageError):
            self.dm.process_password_change_attempt("guy1", "elixir", "newpwd")

        with pytest.raises(NormalUsageError):
            self.dm.authenticate_with_credentials("guy1", "elixir")
        self.dm.authenticate_with_credentials("guy1", "newpwd")



    @for_core_module(GameViews)
    def test_game_view_registries(self):

        assert self.dm.get_event_count("SYNC_GAME_VIEW_DATA_CALLED") == 0 # event stats have been cleared above

        views_dict = self.dm.get_game_views()
        assert views_dict is not self.dm.GAME_VIEWS_REGISTRY # copy

        activable_views_dict = self.dm.get_activable_views()
        assert activable_views_dict is not self.dm.ACTIVABLE_VIEWS_REGISTRY # copy
        assert set(activable_views_dict.keys()) < set(self.dm.get_game_views().keys())

        random_view, random_klass = activable_views_dict.items()[0]

        # instantiation works for both names and classes
        view = self.dm.instantiate_game_view(random_view)
        assert isinstance(view, AbstractGameView)
        view = self.dm.instantiate_game_view(activable_views_dict[random_view])
        assert isinstance(view, AbstractGameView)

        with pytest.raises(AbnormalUsageError):
            self.dm.set_activated_game_views(["aaa", random_view])

        self.dm.set_activated_game_views([])
        assert not self.dm.is_game_view_activated(random_view)
        self.dm.set_activated_game_views([random_view])
        assert self.dm.is_game_view_activated(random_view)


        # access-token retriever shortcut works OK
        assert self.dm.user.is_anonymous
        token = self.dm.get_game_view_access_token(views.homepage.NAME)
        assert token == AccessResult.available
        token = self.dm.get_game_view_access_token(views.view_sales)
        assert token == AccessResult.authentication_required


        # test registry resync
        del self.dm.ACTIVABLE_VIEWS_REGISTRY[random_view] # class-level registry
        self.dm.sync_game_view_data()
        assert not self.dm.is_game_view_activated(random_view) # cleanup occurred
        assert self.dm.get_event_count("SYNC_GAME_VIEW_DATA_CALLED") == 1

        with temp_datamanager(TEST_GAME_INSTANCE_ID, self.request) as _dm2:
            assert _dm2.get_event_count("SYNC_GAME_VIEW_DATA_CALLED") == 1 # sync well called at init!!

        self.dm.ACTIVABLE_VIEWS_REGISTRY[random_view] = random_klass # test cleanup


        # test admin form tokens
        assert "admin_dashboard.choose_activated_views" in self.dm.get_admin_widget_identifiers()

        assert self.dm.resolve_admin_widget_identifier("") is None
        assert self.dm.resolve_admin_widget_identifier("qsdqsd") is None
        assert self.dm.resolve_admin_widget_identifier("qsdqsd.choose_activated_views") is None
        assert self.dm.resolve_admin_widget_identifier("admin_dashboard.") is None
        assert self.dm.resolve_admin_widget_identifier("admin_dashboard.qsdqsd") is None

        from pychronia_game.views import admin_dashboard
        components = self.dm.resolve_admin_widget_identifier("admin_dashboard.choose_activated_views")
        assert len(components) == 2
        assert isinstance(components[0], admin_dashboard.klass)
        assert components[1] == "choose_activated_views"


    @for_core_module(SpecialAbilities)
    def test_special_abilities_registry(self):

        abilities = self.dm.get_abilities()
        assert abilities is not self.dm.ABILITIES_REGISTRY # copy
        assert "runic_translation" in abilities

        @register_view
        class PrivateTestAbility(AbstractAbility):

            TITLE = _lazy("Private dummy ability")
            NAME = "_private_dummy_ability"
            GAME_ACTIONS = {}
            TEMPLATE = "base_main.html" # must exist
            ACCESS = UserAccess.anonymous
            REQUIRES_CHARACTER_PERMISSION = False
            ALWAYS_ACTIVATED = False


            def get_template_vars(self, previous_form_data=None):
                return {'page_title': "hello", }

            @classmethod
            def _setup_ability_settings(cls, settings):
                settings.setdefault("myvalue", "True")
                cls._LATE_ABILITY_SETUP_DONE = 65

            def _setup_private_ability_data(self, private_data):
                pass

            def _check_data_sanity(self, strict=False):
                settings = self.settings
                assert settings["myvalue"] == "True"


        assert "_private_dummy_ability" in self.dm.get_abilities() # auto-registration of dummy test ability
        self.dm.rollback()
        with pytest.raises(KeyError):
            self.dm.get_ability_data("_private_dummy_ability") # ability not yet setup in ZODB


        with temp_datamanager(TEST_GAME_INSTANCE_ID, self.request) as _dm:
            assert "_private_dummy_ability" in _dm.get_abilities()
            with pytest.raises(KeyError):
                assert _dm.get_ability_data("_private_dummy_ability") # no hotplug synchronization for abilities ATM
            assert not hasattr(PrivateTestAbility, "_LATE_ABILITY_SETUP_DONE")

        del GameDataManager.ABILITIES_REGISTRY["_private_dummy_ability"] # important cleanup!!!
        del GameDataManager.GAME_VIEWS_REGISTRY["_private_dummy_ability"] # important cleanup!!!



    @for_core_module(StaticPages)
    def test_static_pages(self):

        EXISTING_HELP_PAGE = "help-homepage"

        utilities.check_is_restructuredtext(self.dm.get_categorized_static_page(category="help_pages", name="view_encyclopedia"))

        assert self.dm.get_categorized_static_page(category="help_pages", name="qskiqsjdqsid") is None
        assert self.dm.get_categorized_static_page(category="badcategory", name="view_encyclopedia") is None

        assert EXISTING_HELP_PAGE in self.dm.get_static_page_names_for_category("help_pages")

        assert "lokon" not in self.dm.get_static_page_names_for_category("help_pages")
        assert "lokon" in self.dm.get_static_page_names_for_category("encyclopedia")

        assert sorted(self.dm.get_static_pages_for_category("help_pages").keys()) == sorted(self.dm.get_static_page_names_for_category("help_pages")) # same "random" sorting

        for key, value in self.dm.get_static_pages_for_category("help_pages").items():
            assert "help_pages" in value["categories"]
            utilities.check_is_slug(key)
            assert key.lower() == key

        self._set_user("guy1")
        assert not self.dm.has_user_accessed_static_page(EXISTING_HELP_PAGE)
        self.dm.mark_static_page_as_accessed(EXISTING_HELP_PAGE)
        assert self.dm.has_user_accessed_static_page(EXISTING_HELP_PAGE)
        self.dm.mark_static_page_as_accessed(EXISTING_HELP_PAGE)
        assert self.dm.has_user_accessed_static_page(EXISTING_HELP_PAGE)



    @for_core_module(GameEvents)
    def test_event_logging(self):
        self._reset_messages()

        self._set_user("guy1")
        events = self.dm.get_game_events()
        self.assertEqual(len(events), 1) # fixture

        self.dm.log_game_event("hello there 1")
        self._set_user("master")
        self.dm.log_game_event("hello there 2", url="/my/url/")
        self.dm.commit()

        events = self.dm.get_game_events()[1:] # skip fixture
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["message"], "hello there 1")
        self.assertEqual(events[0]["username"], "guy1")
        self.assertEqual(events[0]["url"], None)
        self.assertEqual(events[1]["message"], "hello there 2")
        self.assertEqual(events[1]["username"], "master")
        self.assertEqual(events[1]["url"], "/my/url/")

        utcnow = datetime.utcnow()
        for event in events:
            self.assertTrue(utcnow - timedelta(seconds=2) < event["time"] <= utcnow)


    @for_datamanager_base
    def test_database_management(self):
        self._reset_messages()

        # test "reset databases" too, in the future
        res = self.dm.dump_zope_database()
        assert isinstance(res, basestring) and len(res) > 1000


    @for_core_module(NightmareCaptchas)
    def test_nightmare_captchas(self):

        captcha_ids = self.dm.get_available_captchas()
        assert captcha_ids

        captcha1 = self.dm.get_selected_captcha(captcha_ids[0])
        captcha2 = self.dm.get_selected_captcha(captcha_ids[-1])
        assert captcha1 != captcha2

        random_captchas = [self.dm.get_random_captcha() for i in range(30)]
        assert set(v["id"] for v in random_captchas) == set(captcha_ids) # unless very bad luck...

        with pytest.raises(AbnormalUsageError):
            self.dm.check_captcha_answer_attempt(captcha_id="unexisting_id", attempt="whatever")

        for captcha in (random_captchas + [captcha1, captcha2]):
            assert set(captcha.keys()) == set("id text image".split()) # no spoiler of answer elements here
            assert self.dm.get_selected_captcha(captcha["id"]) == captcha
            with pytest.raises(NormalUsageError):
                self.dm.check_captcha_answer_attempt(captcha["id"], "")
            with pytest.raises(NormalUsageError):
                self.dm.check_captcha_answer_attempt(captcha["id"], "random stuff ")

            _full_captch_data = self.dm.data["nightmare_captchas"][captcha["id"]]
            answer = "  " + _full_captch_data["answer"].upper() + " " # case and spaces are not important
            res = self.dm.check_captcha_answer_attempt(captcha["id"], answer)
            assert res == _full_captch_data["explanation"] # sucess


    @for_core_module(NovaltyTracker)
    def test_novelty_tracker(self):

        assert self.dm.get_novelty_registry() == {}

        assert self.dm.access_novelty("guest", "qdq|sd") is None

        assert self.dm.access_novelty("master", "qdq|sd")
        assert self.dm.access_novelty("guy1", "qdq|sd")

        assert self.dm.access_novelty("guy1", "qsdffsdf")
        assert not self.dm.access_novelty("guy1", "qsdffsdf") # duplicate OK
        assert self.dm.access_novelty("guy3", "qsdffsdf")
        assert self.dm.access_novelty("guy2", "qsdffsdf")

        assert self.dm.access_novelty("guy4", "dllll", category="mycat")

        #print (self.dm.get_novelty_registry())

        assert self.dm.has_accessed_novelty("guest", "qdq|sd")
        assert self.dm.has_accessed_novelty("guest", "OAUIATAUATUY") # ALWAYS for anonymous, no novelty display

        assert self.dm.has_accessed_novelty("master", "qdq|sd")
        assert self.dm.has_accessed_novelty("guy1", "qdq|sd")
        assert self.dm.has_accessed_novelty("guy1", "qsdffsdf")
        assert not self.dm.has_accessed_novelty("guy1", "qsdffsdf", category="whatever_else")

        assert not self.dm.has_accessed_novelty("guy1", "sdfdfsdkksdfksdkf")
        assert not self.dm.has_accessed_novelty("guy1", "dllll", category="mycat")
        assert self.dm.has_accessed_novelty("guy4", "dllll", category="mycat")
        assert not self.dm.has_accessed_novelty("guy4", "dllll", category="myCat") # case sensitive category
        assert not self.dm.has_accessed_novelty("guy4", "dlllL", category="mycat") # case sensitive key

        # this method's input is not checked by coherency routines, so let's ensure it's protected...
        with pytest.raises(AssertionError):
            self.dm.has_accessed_novelty("badusername", "qsdffsdf")
        with pytest.raises(AssertionError):
            self.dm.has_accessed_novelty("guy1", "qsdf fsdf")

        #print (self.dm.get_novelty_registry())

        assert self.dm.get_novelty_registry() == {("default", u'qsdffsdf'): [u'guy1', u'guy3', u'guy2'], # NO guest (anonymous) HERE (ignored)
                                                  ("default", u'qdq|sd'): [u'master', u'guy1'],
                                                  ("mycat", u'dllll'): [u'guy4']}

        self.dm.reset_novelty_accesses('qdq|sd')
        self.dm.reset_novelty_accesses('unexistingname') # ignored

        assert self.dm.get_novelty_registry() == {("default", u'qsdffsdf'): [u'guy1', u'guy3', u'guy2'],
                                                  ("mycat", u'dllll'): [u'guy4']}
        assert not self.dm.has_accessed_novelty("guy1", 'qdq|sd')
        assert self.dm.has_accessed_novelty("guy1", 'qsdffsdf')



class TestHttpRequests(BaseGameTestCase):

    def _master_auth(self):

        master_login = self.dm.get_global_parameter("master_login")
        login_page = reverse("pychronia_game.views.login", kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID))
        response = self.client.get(login_page) # to set preliminary cookies
        self.assertEqual(response.status_code, 200)

        response = self.client.post(login_page, data=dict(secret_username=master_login, secret_password=self.dm.get_global_parameter("master_password")))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, ROOT_GAME_URL + "/")

        assert self.client.session[SESSION_TICKET_KEY] == {'game_instance_id': TEST_GAME_INSTANCE_ID, 'impersonation_target': None,
                                                                'impersonation_writability': None, 'game_username': master_login}

        self.assertTrue(self.client.cookies["sessionid"])


    def _player_auth(self, username):


        login_page = reverse("pychronia_game.views.login", kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID))
        response = self.client.get(login_page) # to set preliminary cookies
        self.assertEqual(response.status_code, 200)

        response = self.client.post(login_page, data=dict(secret_username=username, secret_password=self.dm.get_character_properties(username)["password"]))

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, ROOT_GAME_URL + "/")

        assert self.client.session[SESSION_TICKET_KEY] == {'game_instance_id': TEST_GAME_INSTANCE_ID, 'impersonation_target': None,
                                                                'impersonation_writability': None, 'game_username': username}

        self.assertTrue(self.client.cookies["sessionid"])


    def _logout(self):

        login_page = reverse("pychronia_game.views.login", kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID))
        logout_page = reverse("pychronia_game.views.logout", kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID))
        response = self.client.get(logout_page, follow=False)

        self.assertEqual(response.status_code, 302)
        assert not self.client.session.has_key(SESSION_TICKET_KEY)

        self.assertRedirects(response, login_page) # beware - LOADS TARGET LOGIN PAGE
        assert self.client.session.has_key("testcookie") # we get it once more thanks to the assertRedirects() above
        assert self.client.session.has_key(SESSION_TICKET_KEY)


    def _simple_master_get_requests(self):
        # FIXME - currently not testing abilities
        self._reset_django_db()

        self.dm.data["global_parameters"]["online_presence_timeout_s"] = 1
        self.dm.data["global_parameters"]["chatroom_presence_timeout_s"] = 1
        self.dm.commit()
        time.sleep(1.2) # online/chatting users list gets emptied

        self._master_auth() # equivalent to self._set_user(self.dm.get_global_parameter("master_login"))

        from django.core.urlresolvers import RegexURLResolver
        from pychronia_game.urls import web_game_urlpatterns # FIXME ADD MOBILE VIEWS

        skipped_patterns = """ability instructions view_help_page profile
                              DATABASE_OPERATIONS FAIL_TEST ajax item_3d_view chat_with_djinn static.serve encrypted_folder 
                              view_single_message logout login secret_question
                              friendship_management wiretapping_management
                              mercenaries_hiring matter_analysis runic_translation 
                              telecom_investigation world_scan artificial_intelligence
                              chess_challenge""".split() # FIXME REMOVE THIS


        views_names = [url._callback_str for url in web_game_urlpatterns
                                   if not isinstance(url, RegexURLResolver) and
                                      not [veto for veto in skipped_patterns if veto in url._callback_str]
                                      and "__" not in url._callback_str] # skip disabled views
        # print views_names


        for view in views_names:
            url = reverse(view, kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID))
            # print(" ====> ", url)
            response = self.client.get(url)
            # print(response._headers) #repr(response.content))
            self.assertEqual(response.status_code, 200, view + " | " + url + " | " + str(response.status_code))


        # these urls and their post data might easily change, beware !
        special_urls = {ROOT_GAME_URL + "/item3dview/sacred_chest/": None,
                        # FIXME NOT YET READYROOT_GAME_URL + "/djinn/": {"djinn": "Pay Rhuss"},
                        ##### FIXME LATER config.MEDIA_URL + "Burned/default_styles.css": None,
                        game_file_url("attachments/image1.png"): None,
                        game_file_url("encrypted/guy2_report/evans/orb.jpg"): None,
                        ROOT_GAME_URL + "/messages/view_single_message/instructions_bewitcher/": None,
                        ROOT_GAME_URL + "/secret_question/guy3/": dict(secret_answer="Fluffy", target_email="guy3@pangea.com"),
                        ROOT_GAME_URL + "/public_webradio/": dict(frequency=self.dm.get_global_parameter("pangea_radio_frequency")),
                        reverse(views.view_help_page, kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID, keyword="help-homepage")): None,
                        }

        for url, value in special_urls.items():
            # print ">>>>>>", url

            if value:
                response = self.client.post(url, data=value)
            else:
                response = self.client.get(url)

            ##print ("WE TRY TO LOAD ", url, response.__dict__)
            self.assertNotContains(response, 'class="error_notifications"', msg_prefix=response.content[0:300])
            self.assertEqual(response.status_code, 200, url + " | " + str(response.status_code))



        ## UNEXISTING response = self.client.get("/media/")
        ##self.assertEqual(response.status_code, 404)

        # no directory index, especially because of hash-protected file serving
        response = self.client.get("/files/") # because ValueError: Unexisting instance u'files'
        self.assertEqual(response.status_code, 404)

        # no direct file access, we need the hash tag
        response = self.client.get("/files/qsdqsdqs/README.txt")
        self.assertEqual(response.status_code, 404)
        response = self.client.get(game_file_url("README.txt"))
        self.assertEqual(response.status_code, 200)

        # user presence is not disrupted by game master
        self.assertEqual(self.dm.get_online_users(), [])
        self.assertEqual(self.dm.get_chatting_users(), [])

        self._logout()


    def test_master_game_started_page_displays(self):
        self.dm.set_game_state(True)
        self._simple_master_get_requests()

    def test_master_game_paused_page_displays(self):
        self.dm.set_game_state(False)
        self._simple_master_get_requests()


    def _test_player_get_requests(self):

        # FIXME - currently not testing abilities

        self._reset_django_db()

        self.dm.data["global_parameters"]["online_presence_timeout_s"] = 1
        self.dm.data["global_parameters"]["chatroom_presence_timeout_s"] = 1
        self.dm.commit()
        time.sleep(1.2) # online/chatting users list gets emptied

        old_state = self.dm.is_game_started()

        self.dm.set_game_state(True)
        self._set_user(None)

        # PLAYER SETUP

        username = "guy2"
        user_money = self.dm.get_character_properties(username)["account"]
        if user_money:
            self.dm.transfer_money_between_characters(username, self.dm.get_global_parameter("bank_name"), user_money) # we empty money
        self.dm.data["character_properties"][username]["permissions"] = PersistentList(["contact_djinns", "manage_agents", "manage_wiretaps"]) # we grant all necessary permissions
        self.dm.commit()
        self.dm.set_game_state(old_state)
        self._player_auth(username)


        # VIEWS SELECTION
        from django.core.urlresolvers import RegexURLResolver
        from pychronia_game.urls import web_game_urlpatterns  # FIXME ADD MOBILE VIEWS
        # we test views for which there is a distinction between master and player
        selected_patterns = """ compose_message view_sales personal_items_slideshow character_profile friendship_management""".split() # TODO LATER network_management contact_djinns
        views = [url._callback_str for url in web_game_urlpatterns if not isinstance(url, RegexURLResolver) and [match for match in selected_patterns if match in url._callback_str]]
        assert len(views) == len(selected_patterns)

        def test_views(views):
            for view in views:
                url = reverse(view, kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID))
                response = self.client.get(url)
                # print response.content
                self.assertEqual(response.status_code, 200, view + " | " + url + " | " + str(response.status_code))

        test_views(views)

        self.dm.set_game_state(True)
        self.dm.transfer_money_between_characters(self.dm.get_global_parameter("bank_name"), username, 1000)
        self.dm.set_game_state(old_state)

        test_views(views)

        self.dm.set_game_state(True)
        gem_name = [key for key, value in self.dm.get_all_items().items() if value["is_gem"] and value["num_items"] >= 6][0] # we only take numerous groups
        self.dm.transfer_object_to_character(gem_name, username)
        self.dm.set_game_state(old_state)

        test_views(views)

        self.assertEqual(self.dm.get_online_users(), [username] if old_state else []) # in paused game, even online users are not updated
        self.assertEqual(self.dm.get_chatting_users(), [])

        self._logout()


    def test_player_game_started_page_displays(self):
        self.dm.set_game_state(True)
        # print "STARTING"
        # import timeit
        # timeit.Timer(self._test_player_get_requests).timeit()
        self._test_player_get_requests()
        # print "OVER"

    def test_player_game_paused_page_displays(self):
        self.dm.set_game_state(False)
        self._test_player_get_requests()


    def test_specific_help_pages_behaviour(self):

        self._reset_django_db()
        self.dm.set_game_state(True)

        # TODO FIXME - use Http403 exceptions instead, when new django version is out !!

        url = reverse(views.view_help_page, kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID,
                                                        keyword=""))
        response = self.client.get(url)
        assert response.status_code == 404

        url = reverse(views.view_help_page, kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID,
                                                        keyword="qsd8778GAVVV"))
        response = self.client.get(url)
        assert response.status_code == 404

        url = reverse(views.view_help_page, kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID,
                                                        keyword="help-homepage"))
        response = self.client.get(url)
        assert response.status_code == 200

        assert self.dm.get_categorized_static_page(self.dm.HELP_CATEGORY, "help-runic_translation")
        url = reverse(views.view_help_page, kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID,
                                                        keyword="help-runic_translation"))
        response = self.client.get(url)
        assert response.status_code == 404 # ACCESS FORBIDDEN

        url = reverse(views.view_help_page, kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID,
                                                        keyword="help-logo_animation"))
        response = self.client.get(url)
        assert response.status_code == 404 # view always available, but no help text available for it


    def test_encyclopedia_behaviour(self):

        self._reset_django_db()

        url_base = reverse(views.view_encyclopedia, kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID))

        for login in ("master", "guy1", None):

            self.dm.set_game_state(False)

            self._set_user(login)
            response = self.client.get(url_base + "?search=animal")
            assert response.status_code == 200
            assert "have access to" in response.content.decode("utf8") # no search results

            self.dm.set_game_state(True)

            self._set_user(login)
            response = self.client.get(url_base)
            assert response.status_code == 200

            url = reverse(views.view_encyclopedia, kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID,
                                                               article_id="lokon"))
            response = self.client.get(url)
            assert response.status_code == 200
            assert "animals" in response.content.decode("utf8")

            response = self.client.get(url_base + "?search=animal")
            assert response.status_code == 200
            # print(repr(response.content))
            assert "results" in response.content.decode("utf8") # several results displayed

            response = self.client.get(url_base + "?search=gerbil")
            assert response.status_code == 302
            assert reverse(views.view_encyclopedia, kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID, article_id="gerbil_species")) in response['Location']


class TestGameViewSystem(BaseGameTestCase):



    def test_form_to_action_argspec_compatibility(self):
        """
        Forms attached to actions must define AT LEAST the fields mandatory in the action callback.
        """

        COMPUTED_VALUES = ["target_names"] # values that are injected in get_normalized_values(), and so invisible until actual processing

        self._set_user("guy1") # later, we'll need to change it depending on abilities instantiated below...
        # all forms must be instantiable, so provided items etc. !
        self.dm.transfer_object_to_character("statue", "guy1")
        wiretapping = self.dm.instantiate_ability("wiretapping")
        wiretapping.perform_lazy_initializations()
        wiretapping.purchase_wiretapping_slot()

        check_done = 0
        for game_view_class in self.dm.GAME_VIEWS_REGISTRY.values():

            game_view = self.dm.instantiate_game_view(game_view_class) # must work for abilities too!
            if hasattr(game_view, "perform_lazy_initializations"):
                game_view.perform_lazy_initializations() # ability object


            for action_name, action_properties in game_view.GAME_ACTIONS.items() + game_view.ADMIN_ACTIONS.items():

                FormClass = action_properties["form_class"]
                if not FormClass:
                    continue # action without predefined form class

                if action_name in game_view.GAME_ACTIONS:
                    form_inst = game_view._instantiate_game_form(action_name)
                else:
                    assert action_name in game_view.ADMIN_ACTIONS
                    form_inst = game_view._instantiate_admin_form(action_name)

                callback_name = action_properties["callback"]
                callback = getattr(game_view, callback_name)

                (args, varargs, varkw, defaults) = inspect.getargspec(callback) # will fail if keyword-only arguments are used, in the future
                if args[0] == "self":
                    args = args[1:] # PB if instance is not called "self"...
                if varkw:
                    args = args[:-1]
                if varargs:
                    args = args[:-1]
                if defaults:
                    args = args[:-len(defaults)] # WRONG if defaults == ()

                for arg_name in args: # remaining ones are mandatory
                    if arg_name in COMPUTED_VALUES:
                        continue
                    fields = form_inst.fields
                    print(fields)
                    assert arg_name in fields # might have been created dynamically at instantiation

                check_done += 1

        assert check_done > 3 # increase that in the future, for safety



    def test_mandatory_access_settings(self):

        # let's not block the home url...
        assert views.homepage.ACCESS == UserAccess.anonymous
        assert views.homepage.ALWAYS_ACTIVATED == True


    def test_access_parameters_normalization(self):

        from pychronia_game.datamanager.abstract_game_view import _normalize_view_access_parameters
        from pychronia_game.common import _undefined

        res = _normalize_view_access_parameters()
        assert res == dict(access=UserAccess.master,
                            requires_character_permission=False,
                            always_activated=True)

        res = _normalize_view_access_parameters(UserAccess.anonymous, True, False)
        assert res == dict(access=UserAccess.anonymous,
                            requires_character_permission=True, # would raise an issue later, in metaclass, because we're in anonymous access
                            always_activated=False)

        res = _normalize_view_access_parameters(UserAccess.anonymous)
        assert res == dict(access=UserAccess.anonymous,
                            requires_character_permission=False,
                            always_activated=False) # even in anonymous access

        res = _normalize_view_access_parameters(UserAccess.character)
        assert res == dict(access=UserAccess.character,
                            requires_character_permission=False,
                            always_activated=False)

        res = _normalize_view_access_parameters(UserAccess.authenticated)
        assert res == dict(access=UserAccess.authenticated,
                            requires_character_permission=False,
                            always_activated=False)

        res = _normalize_view_access_parameters(UserAccess.master)
        assert res == dict(access=UserAccess.master,
                            requires_character_permission=False,
                            always_activated=True) # logical

        res = _normalize_view_access_parameters(UserAccess.character, requires_character_permission=True)
        assert res == dict(access=UserAccess.character,
                            requires_character_permission=True,
                            always_activated=False)


        class myview:
            ACCESS = UserAccess.authenticated
            REQUIRES_CHARACTER_PERMISSION = True
            ALWAYS_ACTIVATED = False

        res = _normalize_view_access_parameters(attach_to=myview)
        assert res == dict(access=UserAccess.authenticated,
                            requires_character_permission=True,
                            always_activated=False)

        with pytest.raises(AssertionError):
            while True:
                a, b, c = [random.choice([_undefined, False]) for i in range(3)]
                if not all((a, b, c)):
                    break # at leats one of them must NOT be _undefined
            _normalize_view_access_parameters(a, b, c, attach_to=myview)


    def test_game_view_registration_decorator(self):

        # case of method registration #

        def my_little_view(request, *args, **kwargs):
            pass

        # stupid cases get rejected in debug mode
        with pytest.raises(AssertionError):
            register_view(my_little_view, access=UserAccess.master, requires_character_permission=True)
        with pytest.raises(AssertionError):
            register_view(my_little_view, access=UserAccess.master, always_activated=False) # master must always access his views!
        with pytest.raises(AssertionError):
            register_view(my_little_view, access=UserAccess.anonymous, requires_character_permission=True)

        klass = register_view(my_little_view, access=UserAccess.master, title=_lazy("jjj"), always_allow_post=True)

        assert issubclass(klass, AbstractGameView)
        assert klass.__name__ == "MyLittleView" # pascal case
        assert klass.NAME == "my_little_view" # snake case
        assert klass.NAME in self.dm.GAME_VIEWS_REGISTRY

        assert klass.ALWAYS_ALLOW_POST == True
        assert AbstractGameView.ALWAYS_ALLOW_POST == False

        with pytest.raises(AssertionError):
            register_view(my_little_view, access=UserAccess.master, title=_lazy("ssss")) # double registration impossible!


        # case of class registration #
        class DummyViewNonGameView(object):
            ACCESS = "sqdqsjkdqskj"
        with pytest.raises(AssertionError):
            register_view(DummyViewNonGameView, title=_lazy("SSS")) # must be a subclass of AbstractGameView


        class DummyView(AbstractGameView):
            TITLE = _lazy("DSDSF")
            NAME = "sdfsdf"
            ACCESS = UserAccess.anonymous
        klass = register_view(DummyView)
        assert isinstance(klass, type)
        register_view(DummyView, title=_lazy("DDD")) # double registration possible, since it's class creation which actually registers it, not that decorator


        class OtherDummyView(AbstractGameView):
            TITLE = _lazy("LJKSG")
            NAME = "sdfsdzadsfsdff"
            ACCESS = UserAccess.anonymous
        with pytest.raises(AssertionError): # when a klass is given, all other arguments become forbidden
            while True:
                a, b, c, d = [random.choice([_undefined, False]) for i in range(4)]
                if not all((a, b, c)):
                    break # at least one of them must NOT be _undefined
            register_view(OtherDummyView, a, b, c, d, title=_lazy("SSS"))



    def test_access_token_computation(self):


        datamanager = self.dm

        def dummy_view_anonymous(request):
            pass
        view_anonymous = register_view(dummy_view_anonymous, access=UserAccess.anonymous, always_activated=False, title=_lazy("Hi"))

        def dummy_view_character(request):
            pass
        view_character = register_view(dummy_view_character, access=UserAccess.character, always_activated=False, title=_lazy("Hi2"))

        def dummy_view_character_permission(request):
            pass
        view_character_permission = register_view(dummy_view_character_permission, access=UserAccess.character, requires_character_permission=True, always_activated=False, title=_lazy("Hi3"))

        def dummy_view_authenticated(request):
            pass
        view_authenticated = register_view(dummy_view_authenticated, access=UserAccess.authenticated, always_activated=False, title=_lazy("Hisss"))

        def dummy_view_master(request):
            pass
        view_master = register_view(dummy_view_master, access=UserAccess.master, always_activated=True, title=_lazy("QQQ")) # always_activated is enforced to True for master views, actually


        # check global disabling of views by game master #
        for username in (None, "guy1", "guy2", self.dm.get_global_parameter("master_login")):
            self._set_user(username)

            for my_view in (view_anonymous, view_character, view_character_permission, view_authenticated): # not view_master

                my_view.klass.ALWAYS_ACTIVATED = False # view is DISABLED ATM
                if not self.dm.is_master():
                    expected = AccessResult.globally_forbidden
                elif my_view.klass.ACCESS == UserAccess.character:
                    expected = AccessResult.authentication_required # master can't access character-only view
                else:
                    expected = AccessResult.available # master bypasses activation check
                assert my_view.get_access_token(datamanager) == expected
                self.dm.set_activated_game_views([my_view.NAME]) # exists in ACTIVABLE_VIEWS_REGISTRY because we registered view with always_activated=True
                assert my_view.get_access_token(datamanager) != AccessResult.globally_forbidden

                my_view.klass.ALWAYS_ACTIVATED = True
                assert my_view.get_access_token(datamanager) != AccessResult.globally_forbidden
                self.dm.set_activated_game_views([]) # RESET
                assert my_view.get_access_token(datamanager) != AccessResult.globally_forbidden


        self._set_user(None)
        assert view_anonymous.get_access_token(datamanager) == AccessResult.available
        assert view_character.get_access_token(datamanager) == AccessResult.authentication_required
        assert view_character_permission.get_access_token(datamanager) == AccessResult.authentication_required
        assert view_authenticated.get_access_token(datamanager) == AccessResult.authentication_required
        assert view_master.get_access_token(datamanager) == AccessResult.authentication_required

        self._set_user("guy1") # has special "access_dummy_view_character_permission" permission
        assert view_anonymous.get_access_token(datamanager) == AccessResult.available
        assert view_character.get_access_token(datamanager) == AccessResult.available
        assert view_character_permission.get_access_token(datamanager) == AccessResult.available
        assert view_authenticated.get_access_token(datamanager) == AccessResult.available
        assert view_master.get_access_token(datamanager) == AccessResult.authentication_required

        self._set_user("guy2") # has NO special "access_dummy_view_character_permission" permission
        assert view_anonymous.get_access_token(datamanager) == AccessResult.available
        assert view_character.get_access_token(datamanager) == AccessResult.available
        assert view_character_permission.get_access_token(datamanager) == AccessResult.permission_required # != authentication required
        assert view_authenticated.get_access_token(datamanager) == AccessResult.available
        assert view_master.get_access_token(datamanager) == AccessResult.authentication_required

        self._set_user(self.dm.get_global_parameter("master_login"))
        assert view_anonymous.get_access_token(datamanager) == AccessResult.available
        assert view_character.get_access_token(datamanager) == AccessResult.authentication_required # master must downgrade to character!!
        assert view_character_permission.get_access_token(datamanager) == AccessResult.authentication_required # master must downgrade to character!!
        assert view_authenticated.get_access_token(datamanager) == AccessResult.available
        assert view_master.get_access_token(datamanager) == AccessResult.available


    def test_action_processing_basics(self):

        bank_name = self.dm.get_global_parameter("bank_name")
        self.dm.transfer_money_between_characters(bank_name, "guy1", amount=1000)

        # BEWARE - below we use another datamanager !!
        view_url = reverse(views.wiretapping_management, kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID))

        # first a "direct action" html call
        request = self.factory.post(view_url, data=dict(_action_="purchase_wiretapping_slot", qsdhqsdh="33"))
        request.datamanager._set_user("guy1")
        wiretapping = request.datamanager.instantiate_ability("wiretapping")
        assert not request.datamanager.get_event_count("TRY_PROCESSING_FORMLESS_GAME_ACTION")
        assert not request.datamanager.get_event_count("PROCESS_HTML_REQUEST")
        response = wiretapping(request)
        assert response.status_code == 200
        assert wiretapping.get_wiretapping_slots_count() == 1
        assert request.datamanager.get_event_count("TRY_PROCESSING_FORMLESS_GAME_ACTION") == 1
        assert request.datamanager.get_event_count("PROCESS_HTML_REQUEST") == 1

        # now in ajax
        request = self.factory.post(view_url, data=dict(_action_="purchase_wiretapping_slot", vcv="33"), HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        request.datamanager._set_user("guy1")
        wiretapping = request.datamanager.instantiate_ability("wiretapping")
        assert not request.datamanager.get_event_count("TRY_PROCESSING_FORMLESS_GAME_ACTION")
        assert not request.datamanager.get_event_count("PROCESS_AJAX_REQUEST")
        response = wiretapping(request)
        assert response.status_code == 200
        assert wiretapping.get_wiretapping_slots_count() == 2
        assert request.datamanager.get_event_count("TRY_PROCESSING_FORMLESS_GAME_ACTION") == 1
        assert request.datamanager.get_event_count("PROCESS_AJAX_REQUEST") == 1

        # now via the abstract form (+ middleware)
        request = self.factory.post(view_url, data=dict(_ability_form="pychronia_game.views.abilities.wiretapping_management_mod.WiretappingTargetsForm",
                                                        target_0="guy3",
                                                        fdfd="33"))
        request.datamanager._set_user("guy1")
        wiretapping = request.datamanager.instantiate_ability("wiretapping")
        assert not request.datamanager.get_event_count("DO_PROCESS_FORM_SUBMISSION")
        assert not request.datamanager.get_event_count("PROCESS_HTML_REQUEST")
        assert not request.datamanager.get_event_count("EXECUTE_GAME_ACTION_WITH_MIDDLEWARES")
        assert request.datamanager.get_wiretapping_targets() == []
        response = wiretapping(request)
        assert response.status_code == 200
        assert wiretapping.get_wiretapping_slots_count() == 2 # unchanged
        assert request.datamanager.get_wiretapping_targets() == ["guy3"]
        assert request.datamanager.get_event_count("DO_PROCESS_FORM_SUBMISSION") == 1
        assert request.datamanager.get_event_count("PROCESS_HTML_REQUEST") == 1
        assert request.datamanager.get_event_count("EXECUTE_GAME_ACTION_WITH_MIDDLEWARES") == 1


    def test_gameview_novelty_tracking(self):

        view_url = reverse(views.runic_translation, kwargs=dict(game_instance_id=TEST_GAME_INSTANCE_ID)) # access == character only

        # first a "direct action" html call
        request = self.factory.post(view_url)

        request.datamanager._set_user("master")

        runic_translation = request.datamanager.instantiate_ability("runic_translation")

        res = runic_translation(request)
        assert res.status_code == 302 # access not allowed

        assert not runic_translation.has_user_accessed_view(runic_translation.datamanager)

        request.datamanager._set_user("guy1")
        request.datamanager.set_activated_game_views([runic_translation.NAME]) # else no access

        res = runic_translation(request)
        assert res.status_code == 200 # access allowed

        assert runic_translation.has_user_accessed_view(runic_translation.datamanager)



class TestActionMiddlewares(BaseGameTestCase):


    def _flatten_explanations(self, list_of_lists_of_strings):
        """
        Also checks for coherency of list_of_lists_of_strings.
        """
        assert isinstance(list_of_lists_of_strings, list) # may be empty
        for l in list_of_lists_of_strings:
            assert l # important -> if a middleware has nothing to say, he musn't include its sublist
            for s in l:
                assert s
                assert isinstance(s, basestring)
        return u"\n".join(u"".join(strs) for strs in list_of_lists_of_strings)


    def _check_full_action_explanations(self, full_list):
        for title, explanations in full_list:
            assert isinstance(title, Promise) and unicode(title)
            assert explanations # NO empty lists here
            assert self._flatten_explanations(explanations)
        return full_list # if caller wants to check non-emptiness


    def test_basic_action_middleware_status(self):

        self._set_user("guy4")

        ability = self.dm.instantiate_ability("dummy_ability")
        ability.perform_lazy_initializations() # normally done while treating HTTP request...

        assert not ability.has_action_middlewares_configured(action_name="middleware_wrapped_test_action")
        assert not ability.is_action_middleware_activated(action_name="middleware_wrapped_test_action", middleware_class=CostlyActionMiddleware)

        ability.reset_test_settings("middleware_wrapped_test_action", CostlyActionMiddleware, dict(is_active=False, money_price=203, gems_price=123))

        assert ability.has_action_middlewares_configured(action_name="middleware_wrapped_test_action")
        assert not ability.is_action_middleware_activated(action_name="middleware_wrapped_test_action", middleware_class=CostlyActionMiddleware)

        ability.reset_test_settings("middleware_wrapped_test_action", CostlyActionMiddleware, dict(is_active=True, money_price=203, gems_price=123))

        assert ability.has_action_middlewares_configured(action_name="middleware_wrapped_test_action")
        assert ability.is_action_middleware_activated(action_name="middleware_wrapped_test_action", middleware_class=CostlyActionMiddleware)



    def test_all_get_middleware_data_explanations(self):

        self._set_user("guy4") # important
        bank_name = self.dm.get_global_parameter("bank_name")
        self.dm.transfer_money_between_characters(bank_name, "guy4", amount=1000)

        ability = self.dm.instantiate_ability("dummy_ability")
        ability.perform_lazy_initializations() # normally done while treating HTTP request...

        assert not ability.has_action_middlewares_configured(action_name="middleware_wrapped_test_action")
        ability.reset_test_settings("middleware_wrapped_test_action", CostlyActionMiddleware, dict(is_active=False, money_price=203, gems_price=123))

        explanations = ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action")
        assert explanations == [] # no middlewares ACTIVATED

        ability.reset_test_settings("middleware_wrapped_test_action", CostlyActionMiddleware, dict(is_active=True, money_price=203, gems_price=123))
        assert ability.has_action_middlewares_configured(action_name="middleware_wrapped_test_action")
        assert ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action") # no pb with non-activated ones

        ability.reset_test_settings("middleware_wrapped_test_action", CountLimitedActionMiddleware, dict(max_per_character=23, max_per_game=33))
        assert ability.has_action_middlewares_configured(action_name="middleware_wrapped_test_action")
        assert ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action") # no pb with non-activated ones

        ability.reset_test_settings("middleware_wrapped_test_action", TimeLimitedActionMiddleware, dict(waiting_period_mn=87, max_uses_per_period=12))
        assert ability.has_action_middlewares_configured(action_name="middleware_wrapped_test_action")
        assert ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action") # no pb with non-activated ones

        assert 18277 == ability.middleware_wrapped_callable1(use_gems=None) # we perform action ONCE

        explanations = ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action")
        explanations = self._flatten_explanations(explanations)
        assert "%s" not in explanations and "%r" not in explanations, explanations

        for stuff in (203, 123, 23, 33, 12, " 1 "):
            assert str(stuff) in explanations
        assert "3941" in explanations, explanations # floor of 45.3 days factor * 87 mn

        ##print(">>>>>|||>>>>>", explanations)


    def test_get_game_actions_explanations(self):

        self._set_user("guy4") # important
        bank_name = self.dm.get_global_parameter("bank_name")
        self.dm.transfer_money_between_characters(bank_name, "guy4", amount=1000)

        view = self.dm.instantiate_game_view("characters_view")
        assert view.get_game_actions_explanations() == [] # has game actions, but no middlewares, because not an ability
        del view

        ability = self.dm.instantiate_ability("dummy_ability")
        ability.perform_lazy_initializations() # normally done while treating HTTP request...


        ability.reset_test_settings("middleware_wrapped_other_test_action", CostlyActionMiddleware, dict(money_price=203, gems_price=123))
        assert self._check_full_action_explanations(ability.get_game_actions_explanations())

        ability.reset_test_settings("middleware_wrapped_other_test_action", CountLimitedActionMiddleware, dict(max_per_character=23, max_per_game=33))
        assert self._check_full_action_explanations(ability.get_game_actions_explanations())

        ability.reset_test_settings("middleware_wrapped_other_test_action", TimeLimitedActionMiddleware, dict(waiting_period_mn=87, max_uses_per_period=12))
        assert self._check_full_action_explanations(ability.get_game_actions_explanations())

        assert True == ability.middleware_wrapped_other_test_action(my_arg=None) # we perform action ONCE
        assert self._check_full_action_explanations(ability.get_game_actions_explanations())


    def test_action_middleware_bypassing(self):
        """
        Actions that have no entry of the ability's middleware settings shouldn't go through the middlewares chain
        """

        self._set_user("guy4") # important

        ability = self.dm.instantiate_ability("dummy_ability")
        ability.perform_lazy_initializations() # normally done while treating HTTP request...

        transactional_processor = ability.execute_game_action_callback # needs transaction watcher else test is buggy...

        assert not self.dm.get_event_count("EXECUTE_GAME_ACTION_WITH_MIDDLEWARES")
        assert not self.dm.get_event_count("TOP_LEVEL_PROCESS_ACTION_THROUGH_MIDDLEWARES")

        res = transactional_processor("non_middleware_action_callable", unfiltered_params=dict(use_gems=True, aaa=33))
        assert res == 23

        assert not self.dm.get_event_count("EXECUTE_GAME_ACTION_WITH_MIDDLEWARES") # BYPASSED
        assert not self.dm.get_event_count("TOP_LEVEL_PROCESS_ACTION_THROUGH_MIDDLEWARES")

        ability.reset_test_settings("non_middleware_action_callable", CountLimitedActionMiddleware, dict(max_per_character=1, max_per_game=12))

        res = transactional_processor("non_middleware_action_callable", unfiltered_params=dict(use_gems=True, aaa=33))
        assert res == 23

        assert self.dm.get_event_count("EXECUTE_GAME_ACTION_WITH_MIDDLEWARES") # NOT BYPASSED, because configured
        assert self.dm.get_event_count("TOP_LEVEL_PROCESS_ACTION_THROUGH_MIDDLEWARES")

        with raises_with_content(NormalUsageError, "exceeded your quota"):
            transactional_processor("non_middleware_action_callable", unfiltered_params=dict(use_gems=True, aaa=33))

        self.dm.rollback()


    def test_costly_action_middleware(self):

        gem_125 = (125, "several_misc_gems2")
        gem_200 = (200, "several_misc_gems")

        # setup
        bank_name = self.dm.get_global_parameter("bank_name")
        self.dm.transfer_money_between_characters(bank_name, "guy4", amount=1000)
        self.dm.transfer_object_to_character("several_misc_gems", "guy4") # 5 * 200 kashes
        self.dm.transfer_object_to_character("several_misc_gems2", "guy4") # 8 * 125 kashes

        props = self.dm.get_character_properties("guy4")
        assert props["account"] == 1000
        utilities.assert_counters_equal(props["gems"], ([gem_125] * 8 + [gem_200] * 5))

        self._set_user("guy4") # important

        ability = self.dm.instantiate_ability("dummy_ability")
        ability.perform_lazy_initializations() # normally done while treating HTTP request...

        assert isinstance(ability, DummyTestAbility)
        assert CostlyActionMiddleware
        self.dm.commit()


        # misconfiguration case #

        ability.reset_test_settings("middleware_wrapped_test_action", CostlyActionMiddleware, dict(money_price=None, gems_price=None))

        for value in (None, [], [gem_125], [gem_200, gem_125]):
            assert ability.middleware_wrapped_callable1(use_gems=value) # no limit is set at all
            assert ability.middleware_wrapped_callable2(value)
            assert ability.non_middleware_action_callable(use_gems=[gem_125])

        assert not self.dm.is_in_transaction()
        self.dm.check_no_pending_transaction()

        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED1") == 4
        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED2") == 4
        assert self.dm.get_event_count("INSIDE_NON_MIDDLEWARE_ACTION_CALLABLE") == 4

        self.dm.clear_all_event_stats()

        assert self._flatten_explanations(ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action"))

        # payment with money #

        for gems_price in (None, 15, 100): # WHATEVER gems prices

            ability.reset_test_settings("middleware_wrapped_test_action", CostlyActionMiddleware, dict(money_price=15, gems_price=gems_price))
            ability.reset_test_data("middleware_wrapped_test_action", CostlyActionMiddleware, dict()) # useless actually for that middleware

            # payments OK
            assert 18277 == ability.middleware_wrapped_callable1(use_gems=random.choice((None, []))) # triggers payment by money
            assert True == ability.middleware_wrapped_callable2(34) # idem, points to the same conf

            # not taken into account - no middlewares here
            assert 23 == ability.non_middleware_action_callable(use_gems=[gem_125])

            # too expensive
            ability.reset_test_settings("middleware_wrapped_test_action", CostlyActionMiddleware, dict(money_price=999, gems_price=gems_price))
            with raises_with_content(NormalUsageError, "in money"):
                ability.middleware_wrapped_callable1(use_gems=random.choice((None, [])))
            with raises_with_content(NormalUsageError, "in money"):
                ability.middleware_wrapped_callable2("helly")

            # not taken into account - no middlewares here
            assert 23 == ability.non_middleware_action_callable(use_gems=[gem_125])

        ability.reset_test_settings("middleware_wrapped_test_action", CostlyActionMiddleware, dict(money_price=53, gems_price=None))
        assert 18277 == ability.middleware_wrapped_callable1(use_gems=[gem_125, gem_125]) # triggers payment by money ANYWAY!

        # we check data coherency
        props = self.dm.get_character_properties("guy4")
        new_money_value = 1000 - 2 * 3 * 15 - 53 # 2 callables * 3 use_gems values * money price, and special 53 kashes payment
        assert props["account"] == new_money_value
        utilities.assert_sets_equal(props["gems"], [gem_125] * 8 + [gem_200] * 5) # unchanged

        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED1") == 4 # 3 + 1 extra call
        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED2") == 3
        assert self.dm.get_event_count("INSIDE_NON_MIDDLEWARE_ACTION_CALLABLE") == 6

        self.dm.clear_all_event_stats()

        assert self._flatten_explanations(ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action"))


        # payment with gems #

        for money_price in (None, 0, 15): # WHATEVER money prices

            ability.reset_test_settings("middleware_wrapped_test_action", CostlyActionMiddleware, dict(money_price=money_price, gems_price=150))
            ability.reset_test_data("middleware_wrapped_test_action", CostlyActionMiddleware, dict()) # useless actually for that middleware

            # payments OK
            assert ability.middleware_wrapped_callable1(use_gems=[gem_200]) # triggers payment by gems

            # not taken into account - no middlewares here
            assert ability.non_middleware_action_callable(use_gems=[gem_125, (128, None), (129, None)])

            # too expensive for current gems given
            with raises_with_content(NormalUsageError, "kashes of gems"):
                ability.middleware_wrapped_callable1(use_gems=[gem_125])

            with raises_with_content(NormalUsageError, "top off"): # we're nice with people who give too much...
                ability.middleware_wrapped_callable1(use_gems=[gem_125, gem_200])

            with raises_with_content(NormalUsageError, "top off"): # that check is done before "whether or not they really own the games"
                ability.middleware_wrapped_callable1(use_gems=[(128, "several_misc_gems2"), (178, None)])

            # some wrong gems in input (even if a sufficient number  of them is OK)
            with raises_with_content(AbnormalUsageError, "don't possess"):
                ability.middleware_wrapped_callable1(use_gems=[(111, None), (125, "stuffs")])

            if not money_price:
                # no fallback to money, when no gems at all in input
                with raises_with_content(NormalUsageError, "kashes of gems"):
                    ability.middleware_wrapped_callable1(use_gems=random.choice((None, [])))
                with raises_with_content(NormalUsageError, "kashes of gems"):
                    ability.middleware_wrapped_callable2([gem_125, gem_125]) # wrong param name

            assert self._flatten_explanations(ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action"))

        assert ability.middleware_wrapped_callable1(use_gems=[gem_200]) # OK
        assert ability.middleware_wrapped_callable1(use_gems=[gem_125, gem_125]) # OK as long as not too many gems for the asset value

        # we check data coherency
        props = self.dm.get_character_properties("guy4")
        assert props["account"] == new_money_value # unchanged
        utilities.assert_sets_equal(props["gems"], [gem_125] * 6 + [gem_200]) # 3 payments with 2 gems, + 2 separate payments

        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED1") == 5 # 3 + 2 extra calls
        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED2") == 0
        assert self.dm.get_event_count("INSIDE_NON_MIDDLEWARE_ACTION_CALLABLE") == 3

        self.dm.clear_all_event_stats()



        # payment with both is possible #

        ability.reset_test_settings("middleware_wrapped_test_action", CostlyActionMiddleware, dict(money_price=11, gems_price=33))
        ability.reset_test_data("middleware_wrapped_test_action", CostlyActionMiddleware, dict()) # useless actually for that middleware

        ability.middleware_wrapped_callable1(use_gems=[gem_200]) # by gems, works even if smaller gems of user would fit better (no paternalism)
        ability.middleware_wrapped_callable1(use_gems=None) # by money
        ability.middleware_wrapped_callable2("hi") # by money
        assert ability.non_middleware_action_callable(use_gems=[gem_125])
        assert ability.non_middleware_action_callable(use_gems=[])

        # we check data coherency
        props = self.dm.get_character_properties("guy4")
        assert props["account"] == new_money_value - 11 * 2
        utilities.assert_sets_equal(props["gems"], [gem_125] * 2) # "200 kashes" gem is out

        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED1") == 2
        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED2") == 1
        assert self.dm.get_event_count("INSIDE_NON_MIDDLEWARE_ACTION_CALLABLE") == 2

        assert self._flatten_explanations(ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action"))


    def test_count_limited_action_middleware(self):


        ability = self.dm.instantiate_ability("dummy_ability")


        # BOTH quotas

        ability.reset_test_settings("middleware_wrapped_test_action", CountLimitedActionMiddleware, dict(max_per_character=3, max_per_game=4))

        self._set_user("guy4") # important
        ability.perform_lazy_initializations() # normally done while treating HTTP request...
        ability.reset_test_data("middleware_wrapped_test_action", CountLimitedActionMiddleware, dict()) # will be filled lazily, on call


        assert 18277 == ability.middleware_wrapped_callable1(2524) # 1 use for guy4
        assert True == ability.middleware_wrapped_callable2(2234) # 2 uses for guy4
        assert 23 == ability.non_middleware_action_callable(use_gems=[125]) # no use
        assert 18277 == ability.middleware_wrapped_callable1(132322) # 3 uses for guy4

        with raises_with_content(NormalUsageError, "exceeded your quota"):
            ability.middleware_wrapped_callable1(2524)

        assert self._flatten_explanations(ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action"))


        self._set_user("guy3") # important
        ability.perform_lazy_initializations() # normally done while treating HTTP request...
        ability.reset_test_data("middleware_wrapped_test_action", CountLimitedActionMiddleware, dict()) # will be filled lazily, on call

        assert ability.middleware_wrapped_callable2(None) # 1 use for guy3
        assert ability.non_middleware_action_callable(use_gems=True) # no use
        with raises_with_content(NormalUsageError, "exceeded the global quota"):
            ability.middleware_wrapped_callable2(11)


        self._set_user("guy4") # important
        with raises_with_content(NormalUsageError, "exceeded the global quota"): # this msg now takes precedence over "private quota" one
            ability.middleware_wrapped_callable1(222)

        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED1") == 2
        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED2") == 2
        assert self.dm.get_event_count("INSIDE_NON_MIDDLEWARE_ACTION_CALLABLE") == 2

        self.dm.clear_all_event_stats()

        assert self._flatten_explanations(ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action"))


        # only per-character quota

        ability.reset_test_settings("middleware_wrapped_test_action", CountLimitedActionMiddleware, dict(max_per_character=3, max_per_game=None))

        self._set_user("guy3") # important
        assert ability.middleware_wrapped_callable2(None) # 2 uses for guy3
        assert ability.middleware_wrapped_callable2(None) # 3 uses for guy3
        with raises_with_content(NormalUsageError, "exceeded your quota"):
            ability.middleware_wrapped_callable2(1111122)

        self._set_user("guy4") # important
        with raises_with_content(NormalUsageError, "exceeded your quota"): # back to private quota message
            ability.middleware_wrapped_callable2(False)
        assert ability.non_middleware_action_callable(None)

        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED1") == 0
        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED2") == 2
        assert self.dm.get_event_count("INSIDE_NON_MIDDLEWARE_ACTION_CALLABLE") == 1
        self.dm.clear_all_event_stats()

        assert self._flatten_explanations(ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action"))


        # only global quota

        ability.reset_test_settings("middleware_wrapped_test_action", CountLimitedActionMiddleware, dict(max_per_character=None, max_per_game=12)) # 6 more than current total

        assert ability.middleware_wrapped_callable1(None) # guy4 still

        self._set_user("guy2") # important
        ability.perform_lazy_initializations()

        for i in range(5):
            assert ability.middleware_wrapped_callable1(None)
        with raises_with_content(NormalUsageError, "exceeded the global quota"):
            ability.middleware_wrapped_callable1(False)
        assert ability.non_middleware_action_callable(None)

        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED1") == 6
        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED2") == 0
        assert self.dm.get_event_count("INSIDE_NON_MIDDLEWARE_ACTION_CALLABLE") == 1
        self.dm.clear_all_event_stats()

        assert self._flatten_explanations(ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action"))


        # no quota (or misconfiguration):

        ability.reset_test_settings("middleware_wrapped_test_action", CountLimitedActionMiddleware,
                                    dict(max_per_character=random.choice((None, 0)), max_per_game=random.choice((None, 0))))

        for username in ("guy2", "guy3", "guy4"):
            self._set_user(username) # important
            for i in range(10):
                assert ability.middleware_wrapped_callable1(None)
                assert ability.middleware_wrapped_callable2(None)
                assert ability.non_middleware_action_callable(None)

        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED1") == 30
        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED2") == 30
        assert self.dm.get_event_count("INSIDE_NON_MIDDLEWARE_ACTION_CALLABLE") == 30

        self.dm.clear_all_event_stats()

        assert ability._get_global_usage_count("middleware_wrapped_test_action") == 72 # usage counts are yet updated
        assert ability._get_global_usage_count("middleware_wrapped_other_test_action") == 0 # important - no collision between action names

        ability.reset_test_settings("middleware_wrapped_test_action", CountLimitedActionMiddleware,
                                    dict(max_per_character=30, max_per_game=73))

        self._set_user("guy2")
        assert ability.middleware_wrapped_callable1(None)
        with raises_with_content(NormalUsageError, "exceeded the global quota"):
            ability.middleware_wrapped_callable1(False) # quota of 75 reached
        assert ability.non_middleware_action_callable(None)

        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED1") == 1
        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED2") == 0
        assert self.dm.get_event_count("INSIDE_NON_MIDDLEWARE_ACTION_CALLABLE") == 1

        assert self._flatten_explanations(ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action"))


    def test_time_limited_action_middleware(self):

        WANTED_FACTOR = 2 # we only double durations below
        params = self.dm.get_global_parameters()
        assert params["game_theoretical_length_days"]
        params["game_theoretical_length_days"] = WANTED_FACTOR


        ability = self.dm.instantiate_ability("dummy_ability")
        self._set_user("guy4") # important
        ability.perform_lazy_initializations() # normally done while treating HTTP request...


        # misconfiguration case #

        waiting_period_mn = random.choice((0, None, 3))
        max_uses_per_period = random.choice((0, None, 3)) if not waiting_period_mn else None

        ability.reset_test_settings("middleware_wrapped_test_action", TimeLimitedActionMiddleware,
                                    dict(waiting_period_mn=waiting_period_mn, max_uses_per_period=max_uses_per_period))
        ability.reset_test_data("middleware_wrapped_test_action", TimeLimitedActionMiddleware, dict()) # will be filled lazily, on call

        for i in range(23):
            assert ability.middleware_wrapped_callable1(None)
            assert ability.middleware_wrapped_callable2(None)
            assert ability.non_middleware_action_callable(None)

        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED1") == 23
        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED2") == 23
        assert self.dm.get_event_count("INSIDE_NON_MIDDLEWARE_ACTION_CALLABLE") == 23
        self.dm.clear_all_event_stats()

        private_data = ability.get_private_middleware_data(action_name="middleware_wrapped_test_action",
                                                           middleware_class=TimeLimitedActionMiddleware)
        assert len(private_data["last_use_times"]) == 2 * 23

        assert self._flatten_explanations(ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action"))


        # normal case #

        ability.reset_test_settings("middleware_wrapped_test_action", TimeLimitedActionMiddleware,
                                    dict(waiting_period_mn=0.02 / WANTED_FACTOR, max_uses_per_period=3)) # 1.2s of waiting time

        for username in ("guy2", "guy3"):
            self._set_user(username) # important
            ability.perform_lazy_initializations() # normally done while treating HTTP request...
            ability.reset_test_data("middleware_wrapped_test_action", TimeLimitedActionMiddleware, dict()) # will be filled lazily, on call

            assert ability.middleware_wrapped_callable1(None)
            assert ability.middleware_wrapped_callable1(12)
            assert ability.middleware_wrapped_callable2(32)
            self.dm.commit() # data was touched, even if not really

            old_last_use_times = ability.get_private_middleware_data("middleware_wrapped_test_action", TimeLimitedActionMiddleware)["last_use_times"]
            res = ability._compute_purged_old_use_times(middleware_settings=ability.get_middleware_settings("middleware_wrapped_test_action", TimeLimitedActionMiddleware),
                                                             last_use_times=old_last_use_times[:])
            assert res == old_last_use_times # unchanged
            del res, old_last_use_times
            self.dm.commit() # data was touched, even if not really changed in place

            with raises_with_content(NormalUsageError, "waiting period"):
                ability.middleware_wrapped_callable1(False) # quota of 3 per period reached
            assert ability.non_middleware_action_callable(None)

            assert self._flatten_explanations(ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action"))

            time.sleep(0.2)


        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED1") == 4
        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED2") == 2
        assert self.dm.get_event_count("INSIDE_NON_MIDDLEWARE_ACTION_CALLABLE") == 2
        self.dm.clear_all_event_stats()


        time.sleep(1.3)

        self._set_user("guy2") # important


        for i in range(7):
            assert ability.middleware_wrapped_callable1(None)
            time.sleep(0.41) # just enough to be under 4 accesses / 1.2s

        assert ability.middleware_wrapped_callable2(None)
        with raises_with_content(NormalUsageError, "waiting period"):
            ability.middleware_wrapped_callable1(False) # quota of 3 per period reached if we hit immediateley

        assert self._flatten_explanations(ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action"))

        time.sleep(0.5)

        old_last_use_times = ability.get_private_middleware_data("middleware_wrapped_test_action", TimeLimitedActionMiddleware)["last_use_times"]
        res = ability._compute_purged_old_use_times(middleware_settings=ability.get_middleware_settings("middleware_wrapped_test_action", TimeLimitedActionMiddleware),
                                                         last_use_times=old_last_use_times[:])
        assert set(res) < set(old_last_use_times) # purged
        del res, old_last_use_times
        # data was touched, even if not really changed in place

        assert ability.middleware_wrapped_callable1(False)
        with raises_with_content(NormalUsageError, "waiting period"):
            ability.middleware_wrapped_callable2(False)
        assert ability.non_middleware_action_callable(None)

        assert self._flatten_explanations(ability.get_middleware_data_explanations(action_name="middleware_wrapped_test_action"))

        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED1") == 8
        assert self.dm.get_event_count("INSIDE_MIDDLEWARE_WRAPPED2") == 1
        assert self.dm.get_event_count("INSIDE_NON_MIDDLEWARE_ACTION_CALLABLE") == 1
        self.dm.clear_all_event_stats()




class TestSpecialAbilities(BaseGameTestCase):

    def test_generic_ability_features(self):
        # ability is half-view half-datamanager, so beware about zodb sessions...

        assert AbstractAbility.__call__ == AbstractGameView.__call__ # must not be overlaoded, since it's decorated to catch exceptions

        assert AbstractAbility.__call__._is_under_readonly_method # NO transaction_watcher, must be available in readonly mode too

        assert AbstractAbility.execute_game_action_callback._is_under_transaction_watcher
        assert AbstractAbility.perform_lazy_initializations._is_under_transaction_watcher # just for tests...
        assert AbstractAbility.process_admin_request._is_under_transaction_watcher


    @for_ability(runic_translation)
    def test_runic_translation(self):

        # TODO - NEED TO WEBTEST BLOCKING OF GEMS NUT NOT NON-OWNED ITEMS


        runic_translation = self.dm.instantiate_ability("runic_translation")

        assert runic_translation.ability_data

        self._reset_messages()

        message = """ hi |there,   | how  are \t you # today,\n| buddy, # are you  \t\n okay ? """

        phrases = runic_translation._tokenize_rune_message(message)
        self.assertEqual(phrases, ['hi', 'there,', 'how are you', 'today,', 'buddy,', 'are you okay ?'])

        self.assertEqual(runic_translation._tokenize_rune_message(""), [])

        """ Too wrong and complicated...
        phrases = self.dm._tokenize_rune_message(message, left_to_right=True, top_to_bottom=False)
        self.assertEqual(phrases, ['are you okay ?', 'today,', 'buddy,', 'hi', 'there,', 'how are you'])

        phrases = self.dm._tokenize_rune_message(message, left_to_right=False, top_to_bottom=True)
        self.assertEqual(phrases, ['how are you', 'there,', 'hi' , 'buddy,', 'today,', 'are you okay ?'])

        phrases = self.dm._tokenize_rune_message(message, left_to_right=False, top_to_bottom=False)
        self.assertEqual(phrases, ['are you okay ?', 'buddy,', 'today,', 'how are you', 'there,', 'hi'])
        """

        translator = runic_translation._build_translation_dictionary("na | tsu | me",
                                                                      "yowh | man | cool")
        self.assertEqual(translator, dict(na="yowh", tsu="man", me="cool"))

        self.assertRaises(Exception, runic_translation._build_translation_dictionary, "na | tsu | me | no",
                          "yowh | man | cool")

        self.assertRaises(Exception, runic_translation._build_translation_dictionary, "me | tsu | me",
                          "yowh | man | cool")

        assert runic_translation.ability_data

        decoded_rune_string = "na  hu,  \t yo la\ttsu ri !\n go"
        translator = {"na hu": "welcome",
                      "yo la tsu": "people"}
        random_words = "hoy ma mi mo mu me".split()
        translated_tokens = runic_translation._try_translating_runes(decoded_rune_string, translator=translator, random_words=random_words)

        self.assertEqual(len(translated_tokens), 4, translated_tokens)
        self.assertEqual(translated_tokens[0:2], ["welcome", "people"])
        for translated_token in translated_tokens[2:4]:
            self.assertTrue(translated_token in random_words)

        # temporary solution to deal with currently untranslated runes... #FIXME
        available_translations = [(item_name, settings) for (item_name, settings) in runic_translation.get_ability_parameter("references").items()
                                    if settings["decoding"].strip()]
        (rune_item, translation_settings) = available_translations[0]

        transcription_attempt = translation_settings["decoding"] # '|' and '#'symbols are automatically cleaned
        expected_result = runic_translation._normalize_string(translation_settings["translation"].replace("#", " ").replace("|", " "))
        translation_result = runic_translation._translate_rune_message(rune_item, transcription_attempt)
        self.assertEqual(translation_result, expected_result)

        self._set_user("guy1")
        runic_translation._process_translation_submission(rune_item, transcription_attempt)

        msgs = self.dm.get_all_queued_messages()
        self.assertEqual(len(msgs), 1)
        msg = msgs[0]
        self.assertEqual(msg["recipient_emails"], ["guy1@pangea.com"])
        self.assertTrue("translation" in msg["body"].lower())

        msgs = self.dm.get_all_dispatched_messages()
        self.assertEqual(len(msgs), 1)
        msg = msgs[0]
        self.assertEqual(msg["sender_email"], "guy1@pangea.com")
        self.assertTrue(transcription_attempt.strip() in msg["body"], (transcription_attempt, msg["body"]))
        self.assertTrue(self.dm.get_global_parameter("master_login") in msg["has_read"])


    @for_ability(house_locking)
    def test_house_locking(self):

        house_locking = self.dm.instantiate_ability("house_locking")
        expected_password = house_locking.get_ability_parameter("house_doors_password")

        self.assertEqual(house_locking.are_house_doors_open(), True) # initial state

        self.assertTrue(house_locking.lock_house_doors())
        self.assertEqual(house_locking.are_house_doors_open(), False)

        self.assertFalse(house_locking.lock_house_doors()) # already locked
        self.assertEqual(house_locking.are_house_doors_open(), False)

        self.assertFalse(house_locking.try_unlocking_house_doors(password="blablabla"))
        self.assertEqual(house_locking.are_house_doors_open(), False)

        self.assertTrue(house_locking.try_unlocking_house_doors(password=expected_password))
        self.assertEqual(house_locking.are_house_doors_open(), True)




    def ___test_agent_hiring(self):
        FIXME
        self._reset_messages()

        spy_cost_money = self.dm.get_global_parameter("spy_cost_money")
        spy_cost_gems = self.dm.get_global_parameter("spy_cost_gems")
        mercenary_cost_money = self.dm.get_global_parameter("mercenary_cost_money")
        mercenary_cost_gems = self.dm.get_global_parameter("mercenary_cost_gems")

        self.dm.get_character_properties("guy1")["gems"] = PersistentList([spy_cost_gems, spy_cost_gems, spy_cost_gems, mercenary_cost_gems])
        self.dm.commit()

        cities = self.dm.get_locations().keys()[0:5]


        # hiring with gems #


        self.assertRaises(Exception, self.dm.hire_remote_agent, "guy1",
                          cities[0], mercenary=False, pay_with_gems=True)

        self.assertRaises(Exception, self.dm.hire_remote_agent, "guy1",
                          cities[0], mercenary=True, pay_with_gems=True, gems_list=[spy_cost_gems]) # mercenary more expensive than spy
        self.assertRaises(Exception, self.dm.hire_remote_agent, "guy1",
                          cities[0], mercenary=False, pay_with_gems=True, gems_list=[mercenary_cost_gems, mercenary_cost_gems])

        self.assertEqual(len(self.dm.get_all_queued_messages()), 0)

        self.dm.hire_remote_agent("guy1", cities[0], mercenary=False, pay_with_gems=True, gems_list=[spy_cost_gems])
        self.assertRaises(Exception, self.dm.hire_remote_agent, "guy1", cities[0],
                          mercenary=False, pay_with_gems=True, gems_list=[spy_cost_gems])

        msgs = self.dm.get_all_queued_messages()
        self.assertEqual(len(msgs), 1)
        msg = msgs[0]
        self.assertEqual(msg["recipient_emails"], ["guy1@masslavia.com"])
        self.assertTrue("report" in msg["body"].lower())

        self.dm.hire_remote_agent("guy1", cities[1], mercenary=True, pay_with_gems=True, gems_list=[spy_cost_gems, spy_cost_gems, mercenary_cost_gems])
        self.assertEqual(self.dm.get_character_properties("guy1")["gems"], [])

        self.assertEqual(len(self.dm.get_all_queued_messages()), 1)

        # hiring with money #
        old_nw_account = self.dm.get_character_properties("guy1")["account"]
        self.dm.transfer_money_between_characters("guy3", "guy1", 2 * mercenary_cost_money) # loyd must have at least that on his account

        self.assertRaises(Exception, self.dm.hire_remote_agent, "guy1",
                          cities[0], mercenary=True, pay_with_gems=False, gems_list=[mercenary_cost_gems])

        self.dm.hire_remote_agent("guy1", cities[2], mercenary=False, pay_with_gems=False)
        self.dm.hire_remote_agent("guy1", cities[2], mercenary=True, pay_with_gems=False)
        self.assertEqual(self.dm.get_locations()[cities[2]]["has_mercenary"], True)
        self.assertEqual(self.dm.get_locations()[cities[2]]["has_spy"], True)

        self.assertEqual(self.dm.get_character_properties("guy1")["account"], old_nw_account + mercenary_cost_money - spy_cost_money)

        self.dm.transfer_money_between_characters("guy1", "guy3", self.dm.get_character_properties("guy1")["account"]) # we empty the account

        self.assertRaises(Exception, self.dm.hire_remote_agent, "guy1",
                          cities[3], mercenary=False, pay_with_gems=False)
        self.assertEqual(self.dm.get_locations()[cities[3]]["has_spy"], False)

        # game master case
        self.dm.hire_remote_agent("master", cities[3], mercenary=True, pay_with_gems=False, gems_list=[])
        self.assertEqual(self.dm.get_locations()[cities[3]]["has_mercenary"], True)
        self.assertEqual(self.dm.get_locations()[cities[3]]["has_spy"], False)


    def ___test_mercenary_intervention(self):
        self._reset_messages()

        cities = self.dm.get_locations().keys()[0:5]
        self.dm.hire_remote_agent("guy1", cities[3], mercenary=True, pay_with_gems=False) # no message queued, since it's not a spy

        self.assertEqual(len(self.dm.get_all_queued_messages()), 0)

        self.assertRaises(dm_module.UsageError, self.dm.trigger_masslavian_mercenary_intervention, "guy1", cities[4], "Please attack this city.") # no mercenary ready

        self.assertEqual(len(self.dm.get_all_queued_messages()), 0)

        self.dm.trigger_masslavian_mercenary_intervention("guy1", cities[3], "Please attack this city.")

        self.assertEqual(len(self.dm.get_all_queued_messages()), 0)

        new_queue = self.dm.get_all_dispatched_messages()
        self.assertEqual(len(new_queue), 1)

        msg = new_queue[0]
        self.assertEqual(msg["sender_email"], "guy1@masslavia.com", msg) # we MUST use a dummy email to prevent forgery here
        self.assertEqual(msg["recipient_emails"], ["masslavian-army@special.com"], msg)
        self.assertTrue(msg["is_certified"], msg)
        self.assertTrue("attack" in msg["body"].lower())
        self.assertTrue("***" in msg["body"].lower())


    def ___test_teldorian_teleportation(self):
        self._reset_messages()

        cities = self.dm.get_locations().keys()[0:6]
        max_actions = self.dm.get_global_parameter("max_teldorian_teleportations")
        self.assertTrue(max_actions >= 2)

        self.assertEqual(len(self.dm.get_all_queued_messages()), 0)

        for i in range(max_actions):
            if i == (max_actions - 1):
                self.dm._add_to_scanned_locations([cities[3]]) # the last attack will be on scanned location !
            self.dm.trigger_teldorian_teleportation("scanner", cities[3], "Please destroy this city.")

        self.assertEqual(len(self.dm.get_all_queued_messages()), 0) # immediate sending performed

        new_queue = self.dm.get_all_dispatched_messages()
        self.assertEqual(len(new_queue), max_actions)

        self.assertTrue("on unscanned" in new_queue[0]["subject"])

        msg = new_queue[-1]
        self.assertEqual(msg["sender_email"], "scanner@teldorium.com", msg) # we MUST use a dummy email to prevent forgery here
        self.assertEqual(msg["recipient_emails"], ["teldorian-army@special.com"], msg)
        self.assertTrue("on scanned" in msg["subject"])
        self.assertTrue(msg["is_certified"], msg)
        self.assertTrue("destroy" in msg["body"].lower())
        self.assertTrue("***" in msg["body"].lower())

        msg = new_queue[-2]
        self.assertTrue("on unscanned" in msg["subject"])

        self.assertEqual(self.dm.get_global_parameter("teldorian_teleportations_done"), self.dm.get_global_parameter("max_teldorian_teleportations"))
        self.assertRaises(dm_module.UsageError, self.dm.trigger_teldorian_teleportation, "scanner", cities[3], "Please destroy this city.") # too many teleportations


    def ___test_acharith_attack(self):
        self._reset_messages()

        cities = self.dm.get_locations().keys()[0:5]

        self.assertEqual(len(self.dm.get_all_queued_messages()), 0)

        self.dm.trigger_acharith_attack("guy2", cities[3], "Please annihilate this city.")

        self.assertEqual(len(self.dm.get_all_queued_messages()), 0)

        new_queue = self.dm.get_all_dispatched_messages()
        self.assertEqual(len(new_queue), 1)

        msg = new_queue[0]
        self.assertEqual(msg["sender_email"], "guy2@acharis.com", msg) # we MUST use a dummy email to prevent forgery here
        self.assertEqual(msg["recipient_emails"], ["acharis-army@special.com"], msg)
        self.assertTrue(msg["is_certified"], msg)
        self.assertTrue("annihilate" in msg["body"].lower())
        self.assertTrue("***" in msg["body"].lower())


    @for_ability(wiretapping_management)
    def test_wiretapping_management(self):

        self._reset_messages()

        self._set_user("guy1") # has all permissions

        char_names = self.dm.get_character_usernames()

        wiretapping = self.dm.instantiate_ability("wiretapping")
        wiretapping.perform_lazy_initializations() # normally done during request processing

        assert wiretapping.get_wiretapping_slots_count() == 0
        for i in range(3):
            wiretapping.purchase_wiretapping_slot()
        assert wiretapping.get_wiretapping_slots_count() == 3

        wiretapping.change_current_user_wiretapping_targets(PersistentList())
        self.assertEqual(wiretapping.get_wiretapping_targets(), [])

        wiretapping.change_current_user_wiretapping_targets([char_names[0], char_names[0], char_names[1]])

        self.assertEqual(set(wiretapping.get_wiretapping_targets()), set([char_names[0], char_names[1]]))
        self.assertEqual(wiretapping.get_listeners_for(char_names[1]), ["guy1"])

        self.assertRaises(UsageError, wiretapping.change_current_user_wiretapping_targets, ["dummy_name"])
        self.assertRaises(UsageError, wiretapping.change_current_user_wiretapping_targets, [char_names[i] for i in range(wiretapping.get_wiretapping_slots_count() + 1)])

        self.assertEqual(set(wiretapping.get_wiretapping_targets()), set([char_names[0], char_names[1]])) # didn't change
        self.assertEqual(wiretapping.get_listeners_for(char_names[1]), ["guy1"])

        # SSL/TLS protection purchase
        assert not self.dm.get_confidentiality_protection_status()
        wiretapping.purchase_confidentiality_protection()
        assert self.dm.get_confidentiality_protection_status()
        with pytest.raises(UsageError):
            wiretapping.purchase_confidentiality_protection() # only possible once
        assert self.dm.get_confidentiality_protection_status()


    def test_world_scan(self):

        # TODO - NEED TO WEBTEST BLOCKING OF GEMS AND NON-OWNED ITEMS

        self._reset_messages()

        assert self.dm.data["abilities"] ["world_scan"]["settings"]["result_delay"]
        self.dm.data["abilities"] ["world_scan"]["settings"]["result_delay"] = 0.03 / 45 # flexible time!
        self.dm.commit()

        scanner = self.dm.instantiate_ability("world_scan")
        scanner.perform_lazy_initializations() # normally done during request processing
        self._set_user("guy1")

        res = scanner._compute_scanning_result("sacred_chest")
        self.assertEqual(res, ["Alifir", "Baynon"])

        with pytest.raises(AssertionError):
            scanner.process_world_scan_submission("several_misc_gems") # no gems allowed here

        # ##self.assertEqual(self.dm.get_global_parameter("scanned_locations"), [])

        self.assertEqual(len(self.dm.get_all_dispatched_messages()), 0)
        self.assertEqual(len(self.dm.get_all_queued_messages()), 0)

        # AUTOMATED SCAN #
        scanner.process_world_scan_submission("sacred_chest")
        # print datetime.utcnow(), "----", self.dm.data["scheduled_actions"]


        msgs = self.dm.get_all_queued_messages()
        self.assertEqual(len(msgs), 1)
        msg = msgs[0]
        # print(">>>>>>", msg)
        self.assertEqual(msg["recipient_emails"], ["guy1@pangea.com"])
        self.assertTrue("scanning" in msg["body"].lower())
        # print(msg["body"])
        self.assertTrue("Alifir" in msg["body"])

        msgs = self.dm.get_all_dispatched_messages()
        self.assertEqual(len(msgs), 1)
        msg = msgs[0]
        self.assertEqual(msg["sender_email"], "guy1@pangea.com")
        self.assertTrue("scan" in msg["body"])
        self.assertTrue(self.dm.get_global_parameter("master_login") in msg["has_read"])

        res = self.dm.process_periodic_tasks()

        assert res == {"messages_dispatched": 0, "actions_executed": 0}

        time.sleep(3)

        self.assertEqual(self.dm.process_periodic_tasks(), {"messages_dispatched": 1, "actions_executed": 0})

        self.assertEqual(self.dm.get_event_count("DELAYED_ACTION_ERROR"), 0)
        self.assertEqual(self.dm.get_event_count("DELAYED_MESSAGE_ERROR"), 0)

        # ##scanned_locations = self.dm.get_global_parameter("scanned_locations")
        # ##self.assertTrue("Alifir" in scanned_locations, scanned_locations)




    def __test_telecom_investigations(self):

        FIXME

        # no reset of initial messages

        initial_length_queued_msgs = len(self.dm.get_all_queued_messages())
        initial_length_sent_msgs = len(self.dm.get_all_dispatched_messages())

        ability = self.dm.instantiate_ability("telecom_investigation")
        ability.perform_lazy_initializations() # normally done during request processing

        """
        assert self.dm.data["abilities"] ["telecom_investigation"]["settings"]["result_delay"]
        self.dm.data["abilities"] ["world_scan"]["settings"]["result_delay"] = 0.03 / 45 # flexible time!
        self.dm.commit()
        """

        scanner = self.dm.instantiate_ability("world_scan")
        scanner.perform_lazy_initializations() # normally done during request processing
        self._set_user("guy1")


        # text processing #

        res = self.dm._corrupt_text_parts("hello ca va bien coco?", (1, 1), "")
        self.assertEqual(res, "hello ... va ... coco?")

        msg = "hello ca va bien coco? Quoi de neuf ici ? Tout est OK ?"
        res = self.dm._corrupt_text_parts(msg, (2, 4), "de neuf ici")
        self.assertTrue("de neuf ici" in res, res)
        self.assertTrue(14 < len(res) < len(msg), len(res))


        # corruption of team intro + personal instructions
        text = self.dm._get_corrupted_introduction("guy2", "SiMoN  BladstaFfulOvza")

        dump = set(text.split())
        parts1 = set(u"Depuis , notre Ordre Acharite fouille Ciel Terre retrouver Trois Orbes".split())
        parts2 = set(u"votre drogues sera aide inestimable cette mission".split())

        self.assertTrue(len(dump ^ parts1) > 2)
        self.assertTrue(len(dump ^ parts2) > 2)

        self.assertTrue("Simon Bladstaffulovza" in text, repr(text))



        # whole inquiry requests

        telecom_investigations_done = self.dm.get_global_parameter("telecom_investigations_done")
        self.assertEqual(telecom_investigations_done, 0)
        max_telecom_investigations = self.dm.get_global_parameter("max_telecom_investigations")

        self.assertRaises(dm_module.UsageError, self.dm.launch_telecom_investigation, "guy2", "guy2")

        self.assertEqual(len(self.dm.get_all_queued_messages()), initial_length_queued_msgs + 0)

        self.dm.launch_telecom_investigation("guy2", "guy2")

        msgs = self.dm.get_all_queued_messages()
        self.assertEqual(len(msgs), initial_length_queued_msgs + 1)
        msg = msgs[-1]
        self.assertEqual(msg["recipient_emails"], ["guy2@sciences.com"])

        msgs = self.dm.get_all_dispatched_messages()
        self.assertEqual(len(msgs), initial_length_sent_msgs + 1)
        msg = msgs[-1]
        self.assertEqual(msg["sender_email"], "guy2@sciences.com")
        self.assertTrue("discover" in msg["body"])
        self.assertTrue(self.dm.get_global_parameter("master_login") in msg["has_read"])

        for i in range(max_telecom_investigations - 1):
            self.dm.launch_telecom_investigation("guy2", "guy3")
        msgs = self.dm.get_all_queued_messages()
        self.assertEqual(len(msgs), initial_length_queued_msgs + max_telecom_investigations)

        self.assertRaises(dm_module.UsageError, self.dm.launch_telecom_investigation, "guy2", "guy3") # max count exceeded



    def test_matter_analysis(self):

        # TODO - NEED TO WEBTEST BLOCKING OF GEMS AND NON-OWNED ITEMS

        self._reset_messages()

        assert self.dm.data["abilities"] ["matter_analysis"]["settings"]["result_delay"]
        self.dm.data["abilities"] ["matter_analysis"]["settings"]["result_delay"] = 0.03 / 45 # flexible time!
        self.dm.commit()

        analyser = self.dm.instantiate_ability("matter_analysis")
        analyser.perform_lazy_initializations() # normally done during request processing
        self._set_user("guy1")
        self.dm.transfer_object_to_character("sacred_chest", "guy1")
        self.dm.transfer_object_to_character("several_misc_gems", "guy1")

        res = analyser._compute_analysis_result("sacred_chest")
        self.assertEqual(res, "same, here stuffs about *sacred* chest")

        with pytest.raises(AssertionError):
            analyser.process_artefact_analysis("several_misc_gems") # no gems allowed here
        with pytest.raises(AssertionError):
            analyser.process_artefact_analysis("statue") # item must be owned by current user

        self.assertEqual(len(self.dm.get_all_dispatched_messages()), 0)
        self.assertEqual(len(self.dm.get_all_queued_messages()), 0)

        # AUTOMATED SCAN #
        analyser.process_artefact_analysis("sacred_chest")


        msgs = self.dm.get_all_queued_messages()
        self.assertEqual(len(msgs), 1)
        msg = msgs[0]
        # print(">>>>>>", msg)
        self.assertEqual(msg["recipient_emails"], ["guy1@pangea.com"])
        self.assertTrue("*sacred* chest" in msg["body"].lower())

        msgs = self.dm.get_all_dispatched_messages()
        self.assertEqual(len(msgs), 1)
        msg = msgs[0]
        self.assertEqual(msg["sender_email"], "guy1@pangea.com")
        self.assertTrue("Please analyse" in msg["body"])
        self.assertTrue(self.dm.get_global_parameter("master_login") in msg["has_read"])

        res = self.dm.process_periodic_tasks()

        assert res == {"messages_dispatched": 0, "actions_executed": 0}

        time.sleep(3)

        self.assertEqual(self.dm.process_periodic_tasks(), {"messages_dispatched": 1, "actions_executed": 0})

        self.assertEqual(self.dm.get_event_count("DELAYED_ACTION_ERROR"), 0)
        self.assertEqual(self.dm.get_event_count("DELAYED_MESSAGE_ERROR"), 0)










        ''' DISABLED FOR NOW
        # MANUAL SCAN #

        self.dm.process_scanning_submission("scanner", "", "dummydescription2")

        msgs = self.dm.get_all_queued_messages()
        self.assertEqual(len(msgs), 0) # still empty

        msgs = self.dm.get_all_dispatched_messages()
        self.assertEqual(len(msgs), 3) # 2 messages from previous operation, + new one
        msg = msgs[2]
        self.assertEqual(msg["sender_email"], "scanner@teldorium.com")
        self.assertTrue("scan" in msg["body"])
        self.assertTrue("dummydescription2" in msg["body"])
        self.assertFalse(self.dm.get_global_parameter("master_login") in msg["has_read"])

        '''


    def ____test_bots(self): # TODO PAKAL PUT BOTS BACK!!!

        bot_name = "Pay Rhuss" # self.dm.data["AI_bots"]["Pay Rhuss"].keys()[0]
        # print bot_name, " --- ",self.dm.data["AI_bots"]["bot_properties"]

        self._reset_messages()

        username = "guy1"

        res = self.dm.get_bot_response(username, bot_name, "hello")
        self.assertTrue("hi" in res.lower())

        res = self.dm.get_bot_response(username, bot_name, "What's your name ?")
        self.assertTrue(bot_name.lower() in res.lower())

        res = self.dm.get_bot_response(username, bot_name, "What's my name ?")
        self.assertTrue(username in res.lower())

        res = self.dm.get_bot_history(bot_name)
        self.assertEqual(len(res), 2)
        self.assertEqual(len(res[0]), 3)
        self.assertEqual(len(res[0]), len(res[1]))

        res = self.dm.get_bot_response(username, bot_name, "do you know where the orbs are ?").lower()
        self.assertTrue("celestial tears" in res, res)

        res = self.dm.get_bot_response(username, bot_name, "Where is loyd georges' orb ?").lower()
        self.assertTrue("father and his future son-in-law" in res, res)

        res = self.dm.get_bot_response(username, bot_name, "who owns the beta orb ?").lower()
        self.assertTrue("underground temple" in res, res)

        res = self.dm.get_bot_response(username, bot_name, "where is the gamma orb ?").lower()
        self.assertTrue("last treasure" in res, res)

        res = self.dm.get_bot_response(username, bot_name, "where is the wife of the guy2 ?").lower()
        self.assertTrue("young reporter" in res, res)

        res = self.dm.get_bot_response(username, bot_name, "who is cynthia ?").lower()
        self.assertTrue("future wife" in res, res)




class TestGameViews(BaseGameTestCase):



    def test_3D_items_display(self):

        for autoreverse in (True, False):

            viewer_settings = dict(levels=2,
                                    per_level=5,
                                    index_steps=5,
                                    index_offset=3,
                                    start_level=1,
                                    file_template="openinglogo/crystal%04d.jpg",
                                    image_width=528,
                                    image_height=409,
                                    mode="object",
                                    x_coefficient=12,
                                    y_coefficient=160,
                                    autoreverse=autoreverse,
                                    rotomatic=150,
                                    music="musics/mymusic.mp3")
            display_data = views._build_display_data_from_viewer_settings(viewer_settings)


            assert "musics/mymusic.mp3" in display_data["music_url"] # authenticated url
            del display_data["music_url"]

            rel_expected_image_urls = [["openinglogo/crystal0003.jpg",
                                       "openinglogo/crystal0008.jpg",
                                       "openinglogo/crystal0013.jpg",
                                       "openinglogo/crystal0018.jpg",
                                       "openinglogo/crystal0023.jpg"],
                                      ["openinglogo/crystal0028.jpg",
                                       "openinglogo/crystal0033.jpg",
                                       "openinglogo/crystal0038.jpg",
                                       "openinglogo/crystal0043.jpg",
                                       "openinglogo/crystal0048.jpg"], ]
            expected_image_urls = [[game_file_url(rel_path) for rel_path in level] for level in rel_expected_image_urls]

            if autoreverse:
                for id, value in enumerate(expected_image_urls):
                    expected_image_urls[id] = value + list(reversed(value))


            # pprint.pprint(display_data["image_urls"])
            # pprint.pprint(expected_image_urls)

            assert display_data["image_urls"] == expected_image_urls

            del display_data["image_urls"]

            assert display_data == dict(levels=2,
                                        per_level=5 if not autoreverse else 10,
                                        x_coefficient=12,
                                        y_coefficient=160,
                                        rotomatic=150,
                                        image_width=528,
                                        image_height=409,
                                        start_level=1,
                                        mode="object")


    @for_gameview(friendship_management)
    def test_friendship_management(self):

        view = self.dm.instantiate_game_view("friendship_management")

        self._set_user("guy1")

        with pytest.raises(AbnormalUsageError):
            assert "Unexisting friendship" in view.do_cancel_friendship("guy2")

        assert "friendship proposal" in view.do_propose_friendship("guy2")
        assert "friendship proposal" in view.do_cancel_friendship("guy2") # cancel proposal only
        assert "friendship proposal" in view.do_propose_friendship("guy2")
        assert "friendship proposal" in view.do_cancel_proposal("guy2")
        assert "friendship proposal" in view.do_propose_friendship("guy2")
        assert "friendship proposal" in view.do_propose_friendship("guy4")
        assert "friendship proposal" in view.do_propose_friendship("guy3")
        with pytest.raises(AbnormalUsageError):
            view.do_propose_friendship("guy2") # duplicate proposal

        self._set_user("guy2")
        assert "now friend with" in view.do_propose_friendship("guy1")
        with pytest.raises(AbnormalUsageError):
            view.do_propose_friendship("guy1") # already friends
        with pytest.raises(AbnormalUsageError):
            view.do_accept_friendship("guy1") # already friends

        self._set_user("guy3")
        assert "now friend" in view.do_accept_friendship("guy1")
        assert "friendship proposal" in view.do_accept_friendship("guy4")
        with pytest.raises(AbnormalUsageError): # too young friendship
            view.do_cancel_friendship("guy1")

        self._set_user("guy4")
        assert "now friend" in view.do_accept_friendship("guy1")

        for pair, params in self.dm.data["friendships"]["sealed"].items():
            params["acceptance_date"] -= timedelta(hours=30) # delay should be 24h in dev
            self.dm.commit()

        self._set_user("guy3")
        assert "friendship with" in view.do_cancel_friendship("guy1")

        if random.choice((True, False)):
            self._set_user("guy1") # whatever side of the friendship acts...
            assert "friendship with" in view.do_cancel_proposal("guy4")
        else:
            self._set_user("guy4")
            assert "friendship with" in view.do_cancel_proposal("guy1")

'''
      # Mega patching, to test that all what has to persist has been committed
        # properly before returning from datamanager

        for name in dir(self.dm):
            if "transaction" in name or name.startswith("_"):
                continue
            attr = getattr(self.dm, name)
            if isinstance(attr, types.MethodType):
                def container(attr):
                    # we need a container to freeze the free variable "attr"
                    def aborter(*args, **kwargs):
                        res = attr(*args, **kwargs)
                        dm_module.transaction.abort() # we ensure all non-transaction-watched data gets lost !
                        print "Forcing abort"
                        return res
                    return aborter
                setattr(self.dm, name, container(attr))
                print "MONKEY PATCHING ", name

'''


""" DEPRECATED
    def __test_message_template_formatting(self):

        self._reset_messages()

        (subject, body, attachment) = self.dm._build_robot_message_content("translation_result", subject_dict=dict(item="myitem"),
                                                               body_dict=dict(original="lalalall", translation="sqsdqsd", exceeding="qsqsdqsd"))
        self.assertTrue(subject)
        self.assertTrue(body)
        self.assertTrue(attachment is None or isinstance(attachment, basestring))

        self.assertEqual(self.dm.get_event_count("MSG_TEMPLATE_FORMATTING_ERROR_1"), 0)
        self.assertEqual(self.dm.get_event_count("MSG_TEMPLATE_FORMATTING_ERROR_2"), 0)

        (subject, body, attachment) = self.dm._build_robot_message_content("translation_result", subject_dict=dict(item="myitem"),
                                                               body_dict=dict(original="lalalall")) # translation missing

        self.assertEqual(self.dm.get_event_count("MSG_TEMPLATE_FORMATTING_ERROR_1"), 1)
        self.assertEqual(self.dm.get_event_count("MSG_TEMPLATE_FORMATTING_ERROR_2"), 0)

        # we won't test the MSG_TEMPLATE_FORMATTING_ERROR_2, as it'd complicate code uselessly
"""



"""
    TEST_DOMAIN = "dummy_domain"
    def _inject_test_domain(self, name=TEST_DOMAIN, **overrides):
        return # TODO FIXME
        properties = dict(
                        show_official_identities=False,
                        victory="victory_masslavia",
                        defeat="defeat_masslavia",
                        prologue_music="prologue_masslavia.mp3",
                        instructions="blablablabla",
                        permissions=[]
                        )
        assert not (set(overrides.keys()) - set(properties.keys())) # don't inject unwanted params
        properties.update(overrides)

        properties = utilities.convert_object_tree(properties, utilities.python_to_zodb_types)
        self.dm.data["domains"][name] = properties
        self.dm.commit()


    TEST_LOGIN = "guy1" # because special private folders etc must exist. 
    def _inject_test_user(self, name=TEST_LOGIN, **overrides):
        return # TODO FIXME
        properties = dict(
                        password=name.upper(),
                        secret_question="What's the ultimate step of consciousness ?",
                        secret_answer="unguessableanswer",

                        domains=[self.TEST_DOMAIN],
                        permissions=[],

                        external_contacts=[],
                        new_messages_notification="new_messages_guy1",

                        account=1000,
                        initial_cold_cash=100,
                        gems=[],

                        official_name="Strange Character",
                        real_life_identity="John Doe",
                        real_life_email="john@doe.com",
                        description="Dummy test account",

                        last_online_time=None,
                        last_chatting_time=None
                       )

        assert not (set(overrides.keys()) - set(properties.keys())) # don't inject unwanted params
        properties.update(overrides)

        properties = utilities.convert_object_tree(properties, utilities.python_to_zodb_types)
        self.dm.data["character_properties"][name] = properties
        self.dm.commit()
    """
