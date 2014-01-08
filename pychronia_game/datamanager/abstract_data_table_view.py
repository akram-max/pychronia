# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import unicode_literals

from pychronia_game.common import *

from .abstract_form import AbstractGameForm
from .abstract_game_view import AbstractGameView
from .datamanager_tools import readonly_method



class AbstractDataTableManagement(AbstractGameView):

    ACCESS = UserAccess.master
    REQUIRES_CHARACTER_PERMISSION = False
    REQUIRES_GLOBAL_PERMISSION = False


    def get_data_table_instance(self):
        raise NotImplementedError("get_data_table_instance")


    def instantiate_table_form(self, table_item=None, previous_form_data=None):
        """
        If not table_item and not previous_form_data, it's necessarily the "new entry" form.
        """

        initial_data = None
        if table_item:
            table_key, table_value = table_item
            initial_data = dict(identifier=table_key)
            initial_data.update(table_value)
            idx = table_key
        else:
            idx = ""

        res = self._instantiate_game_form(new_action_name="submit_item",
                                     previous_form_data=previous_form_data,
                                     initial_data=initial_data,
                                     form_options=dict(auto_id="id_%s_%%s" % slugify(idx))) # needed by select2 to wrap fields

        return res


    def submit_item(self, previous_identifier, identifier, **data):

        table = self.get_data_table_instance()

        # insertion and update are the same
        table[identifier] = data

        # cleanup in case of renaming
        if previous_identifier and previous_identifier != identifier:
            if previous_identifier in table:
                del table[previous_identifier]
            else:
                self.logger.critical("Wrong previous_identifier submitted in StaticPagesManagement: %r", previous_identifier)

        return _("Entry '%s' properly submitted") % identifier


    def delete_item(self, deleted_item):
        table = self.get_data_table_instance()

        if not deleted_item or deleted_item not in table:
            raise AbnormalUsageError(_("Entry '%s' not found") % deleted_item)
        del table[deleted_item]
        return _("Entry '%s' properly deleted") % deleted_item


    @readonly_method
    def get_template_vars(self, previous_form_data=None):

        table = self.get_data_table_instance()
        mutable_table_items = table.get_all_data(as_sorted_list=True, mutability=True)
        immutable_table_items = table.get_all_data(as_sorted_list=True, mutability=False)

        concerned_identifier = None
        if previous_form_data and not previous_form_data.action_successful:
            concerned_identifier = self.request.POST.get("previous_identifier", "") # empty string if it was a new item

        forms = [("", self.instantiate_table_form(previous_form_data=(previous_form_data if concerned_identifier == "" else None)))] # form for new table entry

        for (table_key, table_value) in mutable_table_items:

            transfered_table_item = (table_key, table_value) # even if previous_form_data is set for that entry
            transfered_previous_form_data = previous_form_data if (concerned_identifier and concerned_identifier == table_key) else None

            new_form = self.instantiate_table_form(table_item=transfered_table_item, previous_form_data=transfered_previous_form_data)
            forms.append((table_key, new_form))

        return dict(immutable_table_items=immutable_table_items,
                    forms=forms)



