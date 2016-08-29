# -*- coding:utf-8 -*-
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import json
import logging

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.shortcuts import redirect
from django.shortcuts import render_to_response
from django.template.context import RequestContext
from networkapiclient.exception import NetworkAPIClientError

from CadVlan.Auth.AuthSession import AuthSession
from CadVlan.EnvironmentVip.form import EnvironmentVipForm
from CadVlan.forms import DeleteForm
from CadVlan.messages import environment_vip_messages
from CadVlan.messages import error_messages
from CadVlan.permissions import ENVIRONMENT_VIP
from CadVlan.templates import ENVIRONMENTVIP_CONF_FORM
from CadVlan.templates import ENVIRONMENTVIP_EDIT
from CadVlan.templates import ENVIRONMENTVIP_FORM
from CadVlan.templates import ENVIRONMENTVIP_LIST
from CadVlan.Util.converters.util import split_to_array
from CadVlan.Util.Decorators import has_perm
from CadVlan.Util.Decorators import log
from CadVlan.Util.Decorators import login_required

logger = logging.getLogger(__name__)


@log
@login_required
@has_perm([{"permission": ENVIRONMENT_VIP, "read": True}])
def list_all(request):

    try:

        environment_vip_list = dict()

        # Get user
        auth = AuthSession(request.session)
        client = auth.get_clientFactory()

        # Get all environment vips from NetworkAPI
        environment_vip_list = client.create_environment_vip().list_all()

        for environment_vip in environment_vip_list.get("environment_vip"):
            environment_vip['is_more'] = str(False)
            option_vip = client.create_option_vip().get_option_vip(
                environment_vip['id'])
            if option_vip is not None:

                ovip = []

                if type(option_vip.get('option_vip')) is dict:
                    option_vip['option_vip'] = [option_vip['option_vip']]

                for option in option_vip['option_vip']:
                    ovip.append(option.get('nome_opcao_txt'))

                if len(ovip) > 3:
                    environment_vip['is_more'] = str(True)

                environment_vip['option_vip'] = ovip

        environment_vip_list['form'] = DeleteForm()

    except NetworkAPIClientError, e:
        logger.error(e)
        messages.add_message(request, messages.ERROR, e)

    return render_to_response(ENVIRONMENTVIP_LIST, environment_vip_list, context_instance=RequestContext(request))


@log
@login_required
@has_perm([{"permission": ENVIRONMENT_VIP, "write": True}])
def delete_all(request):

    if request.method == 'POST':

        form = DeleteForm(request.POST)

        if form.is_valid():

            # Get user
            auth = AuthSession(request.session)
            client_evip = auth.get_clientFactory().create_environment_vip()

            # All ids to be deleted
            ids = split_to_array(form.cleaned_data['ids'])

            # All messages to display
            error_list = list()

            # Control others exceptions
            have_errors = False

            # For each script selected to remove
            for id_environment_vip in ids:
                try:

                    # Execute in NetworkAPI
                    client_evip.remove(id_environment_vip)

                except NetworkAPIClientError, e:
                    logger.error(e)
                    messages.add_message(request, messages.ERROR, e)
                    have_errors = True
                    break

            # If cant remove nothing
            if len(error_list) == len(ids):
                messages.add_message(
                    request, messages.ERROR, error_messages.get("can_not_remove_all"))

            # If cant remove someones
            elif len(error_list) > 0:
                msg = ""
                for id_error in error_list:
                    msg = msg + id_error + ", "

                msg = error_messages.get("can_not_remove") % msg[:-2]

                messages.add_message(request, messages.WARNING, msg)

            # If all has ben removed
            elif have_errors is False:
                messages.add_message(
                    request, messages.SUCCESS, environment_vip_messages.get("success_remove"))

            else:
                messages.add_message(
                    request, messages.SUCCESS, error_messages.get("can_not_remove_error"))

        else:
            messages.add_message(
                request, messages.ERROR, error_messages.get("select_one"))

    # Redirect to list_all action
    return redirect('environment-vip.list')


@log
@login_required
@has_perm([{"permission": ENVIRONMENT_VIP, "write": True}])
def add_form(request):

    try:

        lists = dict()
        lists['action'] = reverse("environment-vip.form")
        # Get user
        auth = AuthSession(request.session)
        client = auth.get_clientFactory()

        options_vip = client.create_option_vip().get_all()
        environmnet_list = client.create_ambiente().list_all()

        if request.method == "POST":

            form = EnvironmentVipForm(options_vip, environmnet_list, request.POST)
            lists['form'] = form

            if form.is_valid():

                finality = form.cleaned_data['finality']
                client_vip = form.cleaned_data['client']
                environment_p44 = form.cleaned_data['environment_p44']
                description = form.cleaned_data['description']
                option_vip = form.cleaned_data['option_vip']
                environment = form.cleaned_data['environment']

                environment_vip = client.create_environment_vip().add(
                    finality,
                    client_vip,
                    environment_p44,
                    description
                )

                for opt in option_vip:
                    client.create_option_vip().associate(
                        opt, environment_vip.get('environment_vip').get('id'))

                for env in environment:
                    client.create_ambiente().associate(
                        env, environment_vip.get('environment_vip').get('id')
                    )

                messages.add_message(
                    request, messages.SUCCESS, environment_vip_messages.get("success_insert"))

                return redirect('environment-vip.list')

        else:

            lists['form'] = EnvironmentVipForm(options_vip, environmnet_list)

    except NetworkAPIClientError, e:
        logger.error(e)
        messages.add_message(request, messages.ERROR, e)

    return render_to_response(ENVIRONMENTVIP_FORM, lists, context_instance=RequestContext(request))


@log
@login_required
@has_perm([{"permission": ENVIRONMENT_VIP, "write": True}])
def conf_form(request, id_environmentvip):

    try:

        lists = dict()
        # Get user
        auth = AuthSession(request.session)
        client = auth.get_clientFactory()

        lists['id_vip'] = id_environmentvip

        environment_vip = client.create_api_environment_vip().get_environment_vip(
            id_environmentvip,
            fields=['id', 'conf']
        ).get('environments_vip')[0]
        conf = json.loads(environment_vip.get("conf"))

        lists['forms'] = conf.get('conf')

        if request.method == "POST":
            dicionario = {}
            dicionario["conf"] = {}

            del conf["conf"]["optionsvip_extended"]
            logger.error("printando json original do banco")
            logger.error(json.dumps(conf))

            logger.error("printando json gerado pela resposta da pagina...")

            # CHAVES
            logger.error("chaves")
            dicionario["conf"]["keys"] = []
            dicionario["conf"]["keys"].append({})
            forms_keys_len = int(request.POST.getlist('forms_keys_len')[0])
            for a in range(forms_keys_len):
                keys_items_len = int(request.POST.getlist('keys_items_len_' + str(a + 1))[0])
                for b in range(keys_items_len):
                    logger.error(request.POST.getlist("chaves_label_" + str(a + 1) + "_" + str(b + 1))[0])
                    logger.error(request.POST.getlist("chaves_input_" + str(a + 1) + "_" + str(b + 1))[0])

                    dicionario["conf"]["keys"][a][request.POST.getlist("chaves_label_" + str(a + 1) + "_" + str(b + 1))[0]] = request.POST.getlist("chaves_input_" + str(a + 1) + "_" + str(b + 1))[0]

            # LAYERS
            dicionario["conf"]["layers"] = []
            logger.error("layers")
            forms_layers_len = int(request.POST.getlist('forms_layers_len')[0])
            for a in range(forms_layers_len):
                dicionario["conf"]["layers"].append({})
                layer_requiments_len = int(request.POST.getlist('layer_requiments_len_' + str(a + 1))[0])
                dicionario["conf"]["layers"][a]["requiments"] = []
                for b in range(layer_requiments_len):
                    # ver o lance do layers input e do _name

                    dicionario["conf"]["layers"][a]["_name"] = request.POST.getlist("layers_input_" + str(a + 1) + "_" + str(b + 1))[0]
                    dicionario["conf"]["layers"][a]["requiments"].append({})

                    logger.error("_name")
                    logger.error(request.POST.getlist("layers_input_" + str(a + 1) + "_" + str(b + 1))[0])

                    requiment_condicionals_b1_len = int(request.POST.getlist("requiment_condicionals_b1_len_" + str(a + 1) + "_" + str(b + 1))[0])
                    dicionario["conf"]["layers"][a]["requiments"][b]["condicionals"] = []
                    for c in range(requiment_condicionals_b1_len):

                        condicional_use_c1_len = int(request.POST.getlist("condicional_use_c1_len_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1))[0])
                        logger.error("var c: " + str(c))
                        dicionario["conf"]["layers"][a]["requiments"][b]["condicionals"].append({})
                        dicionario["conf"]["layers"][a]["requiments"][b]["condicionals"][c]["use"] = []
                        dicionario["conf"]["layers"][a]["requiments"][b]["condicionals"][c]["validations"] = []

                        for d in range(condicional_use_c1_len):
                            dicionario["conf"]["layers"][a]["requiments"][b]["condicionals"][c]["use"].append({})
                            # errado eu acho dicionario["conf"]["layers"][a]["requiments"][b]["condicionals"][c]["validations"].append({})

                            dicionario["conf"]["layers"][a]["requiments"][b]["condicionals"][c]["use"][d]["_name"] = request.POST.getlist("layers_input_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1) + "_" + str(d + 1))[0]
                            dicionario["conf"]["layers"][a]["requiments"][b]["condicionals"][c]["use"][d]["definitions"] = []
                            dicionario["conf"]["layers"][a]["requiments"][b]["condicionals"][c]["use"][d]["eqpts"] = []

                            logger.error("_name")
                            logger.error(request.POST.getlist("layers_input_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1) + "_" + str(d + 1))[0])

                            logger.error("eqpts")
                            form_eqpts_len = int(request.POST.getlist("form_eqpts_len_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1) + "_" + str(d + 1))[0])
                            for e in range(form_eqpts_len):
                                dicionario["conf"]["layers"][a]["requiments"][b]["condicionals"][c]["use"][d]["eqpts"].append(int(request.POST.getlist("layers_input_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1) + "_" + str(d + 1) + "_" + str(e + 1))[0]))

                                logger.error(request.POST.getlist("layers_input_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1) + "_" + str(d + 1) + "_" + str(e + 1))[0])

                            logger.error("definitions")
                            form_definitions_len = int(request.POST.getlist("form_definitions_len_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1) + "_" + str(d + 1))[0])
                            for e in range(form_definitions_len):
                                definition_items_len = int(request.POST.getlist("definition_items_len_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1) + "_" + str(d + 1) + "_" + str(e + 1))[0])
                                dicionario["conf"]["layers"][a]["requiments"][b]["condicionals"][c]["use"][d]["definitions"].append({})

                                for f in range(definition_items_len):
                                    dicionario["conf"]["layers"][a]["requiments"][b]["condicionals"][c]["use"][d]["definitions"][e][request.POST.getlist("layers_label_d1_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1) + "_" + str(d + 1) + "_" + str(e + 1) + "_" + str(f + 1))[0]] = request.POST.getlist("layers_input_d1_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1) + "_" + str(d + 1) + "_" + str(e + 1) + "_" + str(f + 1))[0]
                                    logger.error(request.POST.getlist("layers_label_d1_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1) + "_" + str(d + 1) + "_" + str(e + 1) + "_" + str(f + 1))[0])
                                    logger.error(request.POST.getlist("layers_input_d1_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1) + "_" + str(d + 1) + "_" + str(e + 1) + "_" + str(f + 1))[0])
                        condicional_validations_c1_len = int(request.POST.getlist("condicional_validations_c1_len_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1))[0])
                        for d in range(condicional_validations_c1_len):
                            form_items_d2_len = int(request.POST.getlist("form_items_d2_len_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1) + "_" + str(d + 1))[0])
                            dicionario["conf"]["layers"][a]["requiments"][b]["condicionals"][c]["validations"].append({})

                            for e in range(form_items_d2_len):
                                dicionario["conf"]["layers"][a]["requiments"][b]["condicionals"][c]["validations"][d][request.POST.getlist("layers_label_d2_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1) + "_" + str(d + 1) + "_" + str(e + 1))[0]] = request.POST.getlist("layers_input_d2_" + str(a + 1) + "_" + str(b + 1) + "_" + str(c + 1) + "_" + str(d + 1) + "_" + str(e + 1))[0]
                                # logger.error(request.POST.getlist("layers_label_d2_"+str(a+1)+"_"+str(b+1)+"_"+str(c+1)+"_"+str(d+1)+"_"+str(e+1))[0])
                                # logger.error(request.POST.getlist("layers_input_d2_"+str(a+1)+"_"+str(b+1)+"_"+str(c+1)+"_"+str(d+1)+"_"+str(e+1))[0])

            # dicionario["conf"]["layers"] = []
            # dicionario["conf"]["layers"].append({})
            # dicionario["conf"]["layers"][0]["requiments"] = []
            # dicionario["conf"]["layers"][0]["requiments"][0] = {}
            # len_forms_layers = int(request.POST.getlist('len_forms_layers')[0])
            # for i in range(len_forms_layers):
            #     len_layer_requiments = int(request.POST.getlist('len_layer_requiments_' + str(i + 1))[0])
            #     for j in range(len_layer_requiments):
            #         pass

            # OPTIONSVIP_EXTENDED
            logger.error("optionsvip_extended")
            dicionario["conf"]["optionsvip_extended"] = []

            forms_optionsvip_extended_requiments_len = int(request.POST.getlist("forms_optionsvip_extended_requiments_len")[0])
            for a in range(forms_optionsvip_extended_requiments_len):
                pass

            if(dicionario == conf):
                logger.error("Eh igual!")
            else:
                logger.error("Nao eh igual")

            # logger.error(dicionario)

            logger.error(json.dumps(dicionario))

            # logger.error(request.POST.getlist('chaves_1')[0])
            # json_str  = form.cleaned_data['json']
            # logger.error("json %s" % json_str)

    except NetworkAPIClientError, e:
        logger.error(e)
        messages.add_message(request, messages.ERROR, e)

    return render_to_response(ENVIRONMENTVIP_CONF_FORM, lists, context_instance=RequestContext(request))


@log
@login_required
@has_perm([{"permission": ENVIRONMENT_VIP, "write": True}])
def edit_form(request, id_environmentvip):

    try:

        lists = dict()
        # Get user
        auth = AuthSession(request.session)
        client = auth.get_clientFactory()

        lists['id_vip'] = id_environmentvip

        options_vip = client.create_option_vip().get_all()
        environmnet_list = client.create_ambiente().list_all()

        options = client.create_option_vip().get_option_vip(id_environmentvip)
        environment_related_list_dict = client.create_ambiente().get_related_environment_list(id_environmentvip)

        options = options.get("option_vip", [])
        environment_related_list_dict = environment_related_list_dict.get('environment_related_list', [])

        if type(options) is dict:
            options = [options]

        if type(environment_related_list_dict) is dict:
            environment_related_list_dict = [environment_related_list_dict]

        environment_id_related_list = [env.get('environment_id') for env in environment_related_list_dict]

        if request.method == "POST":

            form = EnvironmentVipForm(options_vip, environmnet_list, request.POST)
            lists['form'] = form

            if form.is_valid():

                finality = form.cleaned_data['finality']
                client_vip = form.cleaned_data['client']
                environment_p44 = form.cleaned_data['environment_p44']
                description = form.cleaned_data['description']
                option_vip_ids = form.cleaned_data['option_vip']
                environment_ids_form = form.cleaned_data['environment']

                client.create_environment_vip().alter(
                    id_environmentvip,
                    finality,
                    client_vip,
                    environment_p44,
                    description)

                for opt in options:
                    client.create_option_vip().disassociate(opt.get('id'), id_environmentvip)
                for opt_id in option_vip_ids:
                    client.create_option_vip().associate(opt_id, id_environmentvip)

                for related_environment_id in environment_id_related_list:
                    if _need_dissassociate_environment(related_environment_id, environment_ids_form):
                        client.create_ambiente().disassociate(related_environment_id, id_environmentvip)

                for environment_form_id in environment_ids_form:
                    if not _environment_already_associated(environment_form_id, environment_id_related_list):
                        client.create_ambiente().associate(environment_form_id, id_environmentvip)

                messages.add_message(
                    request, messages.SUCCESS, environment_vip_messages.get("sucess_edit"))

                return redirect('environment-vip.list')
        # GET
        else:
            # Build form with environment vip data for id_environmentvip
            environment_vip = client.create_environment_vip().search(id_environmentvip)
            environment_vip = environment_vip.get("environment_vip")

            opts = []

            for opt in options:
                opts.append(opt.get('id'))

            lists['form'] = EnvironmentVipForm(options_vip, environmnet_list, initial={"id": environment_vip.get("id"),
                                                                                       "finality": environment_vip.get("finalidade_txt"),
                                                                                       "client": environment_vip.get("cliente_txt"),
                                                                                       "environment_p44": environment_vip.get("ambiente_p44_txt"),
                                                                                       "description": environment_vip.get("description"),
                                                                                       "option_vip": opts,
                                                                                       "environment": environment_id_related_list})
    except NetworkAPIClientError, e:
        logger.error(e)
        messages.add_message(request, messages.ERROR, e)

    return render_to_response(ENVIRONMENTVIP_EDIT, lists, context_instance=RequestContext(request))


def _need_dissassociate_environment(related_environment_id, form_ids_list):
    need = related_environment_id not in form_ids_list
    return need


def _environment_already_associated(environment_form_id, environment_related_list):
    linked = environment_form_id in environment_related_list
    return linked
