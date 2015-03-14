

SCRIPTDIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

export PYTHONPATH="$SCRIPTDIR:$SCRIPTDIR/dependencies"

if [ -z "$DJANGO_SETTINGS_MODULE" ]
then
    export DJANGO_SETTINGS_MODULE=pychronia_settings
fi