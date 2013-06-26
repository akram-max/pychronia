# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals

from pychronia_game.common import *

from pychronia_game.datamanager.abstract_ability import AbstractAbility
from pychronia_game.forms import ArtefactForm, UninstantiableFormError
from pychronia_game.datamanager import readonly_method, \
    transaction_watcher

'''
class PersonalItemForm(AbstractGameForm):

    def __init__(self, datamanager, *args, **kwargs):
        super(PersonalItemForm, self).__init__(datamanager, *args, **kwargs)

        _objects = datamanager.get_available_items_for_user()
        _objects_choices = [("", _("Choose..."))] + [(item_name, _objects[item_name]["title"]) for item_name in sorted(_objects.keys())]

        self.fields["item_name"] = forms.ChoiceField(label=_lazy(u"Item"), choices=_objects_choices)

        assert self.fields.keyOrder # if reordering needed
'''


class MatterAnalysisAbility(AbstractAbility):

    TITLE = _lazy("Matter Analysis")
    NAME = "matter_analysis"

    GAME_ACTIONS = dict(process_artefact=dict(title=_lazy("Process artefact analysis"),
                                                      form_class=ArtefactForm,
                                                      callback="process_artefact_analysis"))


    TEMPLATE = "abilities/matter_analysis.html"

    ACCESS = UserAccess.character
    REQUIRES_CHARACTER_PERMISSION = False
    ALWAYS_ACTIVATED = True


    def get_template_vars(self, previous_form_data=None):

        # for now we don't exclude objects already analysed, players just have to take care !
        try:
            item_form = self._instantiate_game_form(new_action_name="process_artefact",
                                                 hide_on_success=True,
                                                 previous_form_data=previous_form_data,
                                                 propagate_errors=True)
            specific_message = None
        except UninstantiableFormError, e:
            item_form = None
            specific_message = unicode(e)

        return {
                 'page_title': _("Deep Matter Analysis"),
                 'item_form': item_form,
                 'specific_message': specific_message, # TODO FIXME DISPLAY THIS
               }



    @readonly_method
    def _compute_analysis_result(self, item_name):
        assert not self.get_item_properties(item_name)["is_gem"], item_name
        report = self.settings["reports"][item_name]
        return report


    @transaction_watcher
    def process_artefact_analysis(self, item_name):

        assert item_name in self.datamanager.get_available_items_for_user(), item_name

        item_title = self.get_item_properties(item_name)["title"]

        remote_email = self.settings["sender_email"]
        local_email = self.get_character_email()

        # dummy request email, to allow wiretapping

        subject = "Deep Analysis Request - item \"%s\"" % item_title
        body = _("Please analyse the physical and biological properties of this item.")
        self.post_message(local_email, remote_email, subject, body, date_or_delay_mn=0, is_read=True)


        # answer from laboratory

        subject = _("<Deep Matter Analysis Report - %(item_title)s>") % SDICT(item_title=item_title)
        body = self._compute_analysis_result(item_name)

        self.post_message(remote_email, local_email, subject, body=body, attachment=None,
                          date_or_delay_mn=self.settings["result_delay"])

        self.log_game_event(_noop("Item '%(item_title)s' sent for deep matter analysis."),
                             PersistentDict(item_title=item_title),
                             url=None)

        return _("Item '%s' successfully submitted, you'll receive the result by email") % item_title



    @classmethod
    def _setup_ability_settings(cls, settings):
        pass  # nothing to do

    def _setup_private_ability_data(self, private_data):
        pass  # nothing to do


    def _check_data_sanity(self, strict=False):

        settings = self.settings

        def reports_checker(reports):
            assert set(reports.keys()) == set(self.get_non_gem_items().keys())
            for body in reports.values():
                utilities.check_is_restructuredtext(body)
            return True

        _reference = dict(
                            sender_email=utilities.check_is_email,
                            result_delay=utilities.check_is_range_or_num,
                            reports=reports_checker,
                         )
        utilities.check_dictionary_with_template(settings, _reference, strict=strict)



'''

@game_player_required(permission="manage_agents")
def network_management(request, template_name='specific_operations/network_management.html'):

    locations = request.datamanager.get_locations() # dictionary


    # we process wiretap management operations
    if request.method == "POST":
        with action_failure_handler(request, _("Hiring operation successful.")):
            location = request.POST["location"]
            mercenary = (request.POST["type"] == "mercenary")
            pay_with_money = request.POST.get("pay_with_money", False)
            selected_gems = [int(gem) for gem in request.POST.getlist("gems_choices")]
            request.datamanager.hire_remote_agent(location, mercenary, not pay_with_money, selected_gems) # free for the game master

    places_with_spies = [key for key in sorted(locations.keys()) if locations[key]['has_spy']]
    places_with_mercenaries = [key for key in sorted(locations.keys()) if locations[key]['has_mercenary']]


    if user.is_master:
        employer_profile = None
        total_gems_value = None
        gems_choices = [] # hire_remote_agent("master") will allow the hiring of agents anyway !
    else:
        employer_profile = request.datamanager.get_character_properties()
        gems = request.datamanager.get_character_properties()["gems"]
        gems_choices = zip(gems, [_("Gem of %d Kashes")%gem for gem in gems])
        total_gems_value = sum(gems)

    return render(request,
                  template_name,
                    {
                     'page_title': _("Agent Network Management"),
                     'global_parameters': request.datamanager.get_global_parameters(), # TODO REMOVE
                     'places_with_spies': places_with_spies,
                     'places_with_mercenaries': places_with_mercenaries,
                     'employer_profile': employer_profile,
                     'total_gems_value': total_gems_value,
                     'hiring_form': forms.AgentHiringForm(request.datamanager, gems_choices)
                    })

     
     
     
     
     
        DEPRECATED
        employer_char = self.datamanager.get_character_properties(employer_name)

        if pay_with_gems:
            if sum(pay_with_gems) < gems_price:
                raise UsageError(_("You need at least %(price)s kashes in gems to hire these agents") % SDICT(gems_price=gems_price))
                # we don't care if the player has given too many gems !

            remaining_gems = utilities.substract_lists(employer_char["gems"], pay_with_gems)

            if remaining_gems is None:
                raise UsageError(_("You don't possess the gems required"))
            else:
                employer_char["gems"] = remaining_gems


        else: # pay with bank money

            if employer_char["account"] < money_price:
                raise UsageError(_("You need at least %(price)s kashes in money to hire these agents") % SDICT(price=money_price))

            #print self.data["global_parameters"]["total_digital_money_spent"], "----",employer_char["account"]

            employer_char["account"] -= money_price
            self.datamanager.data["global_parameters"]["total_digital_money_spent"] += money_price

            #print self.data["global_parameters"]["total_digital_money_spent"], "----",employer_char["account"]




    @transaction_watcher
    def ____process_spy_activation(self, location):
        # USELESS ?
        employer_name = self.datamanager.player.username
        
        location_data = self.datamanager.get_locations()[location]
        
        spy_message = location_data["spy_message"].strip()
        spy_audio = location_data["spy_audio"]
        #print "ACTIVATING SPY %s with message %s" % (city_name, spy_message)

        sender_email = "message-forwarder@masslavia.com"
        recipient_emails = self.get_character_email(employer_name)
        subject = _("<Spying Report - %(city_name)s>") % SDICT(city_name=location.capitalize())

        default_message = _("*Report from your spies of %(city_name)s*") % SDICT(city_name=location.capitalize())

        if spy_audio:
            body = default_message
            attachment = game_file_url("spy_reports/spy_" + location.lower() + ".mp3")
        else:
            body = default_message + "\n\n-------\n\n" + spy_message
            attachment = None

        self.post_message(sender_email, recipient_emails, subject, body, attachment,
                          date_or_delay_mn=self.get_global_parameter("spy_report_delays"))


        '''