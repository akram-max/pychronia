

from ._test_settings import *



DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(TEST_DIR, "django.db")
    }
}


ZODB_FILE = os.path.join(TEST_DIR, "gamedata.fs")



def GAME_INITIAL_FIXTURE_SCRIPT(dm):
    
    # we activate ALL views
    dm.set_activated_game_views(dm.ACTIVABLE_VIEWS_REGISTRY.keys())

    # we give guy1 access to everything
    dm.update_permissions("guy1", list(dm.PERMISSIONS_REGISTRY))

    # we can see all articles
    dm.set_encyclopedia_index_visibility(True)
