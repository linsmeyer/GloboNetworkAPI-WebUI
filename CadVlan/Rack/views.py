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

import ast
import operator
import logging

from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import render_to_response, redirect
from django.template.context import RequestContext
from django.views.decorators.csrf import csrf_protect

from CadVlan.Acl import acl
from CadVlan.Auth.AuthSession import AuthSession
from CadVlan.forms import CriarVlanAmbForm, DeleteForm, ConfigForm, AplicarForm, AlocarForm
from CadVlan.messages import error_messages, rack_messages, environment_messages
from CadVlan.permissions import EQUIPMENT_MANAGEMENT
from CadVlan.Rack.forms import RackForm
from CadVlan.templates import RACK_EDIT, RACK_FORM, RACK_VIEW_AJAX, DC_FORM, DCROOM_FORM, DCROOM_ENV_FORM, \
    DCROOM_VLANS_FORM, DCROOM_BGP_FORM, MENU
from CadVlan.Util.Decorators import log, login_required, has_perm
from CadVlan.Util.git import GITCommandError
from CadVlan.Util.utility import check_regex, DataTablePaginator, validates_dict

from networkapiclient.exception import NomeRackDuplicadoError, RackAllreadyConfigError, RacksError, \
    InvalidParameterError, NetworkAPIClientError, NumeroRackDuplicadoError

logger = logging.getLogger(__name__)


def proximo_rack(racks):

    rack_anterior = -1
    racks = racks.get('rack')

    lists = list()
    for rack in racks:
        lists.append(int(rack.get('numero')))
    lists.sort()

    for num in lists:
        if num > rack_anterior:
            rack_anterior = rack_anterior + 1
            if not num == rack_anterior:
                return str(rack_anterior)

    rack_anterior = rack_anterior + 1
    if rack_anterior > 119:
        return ''
    return str(rack_anterior)


def validar_mac(mac):

    if not mac=='':
        if not (mac.count(':') == 5):
            raise InvalidParameterError(u'Endereco MAC invalido. Formato: FF:FF:FF:FF:FF:FF')
        mac_val = mac.split(':')
        if ((len(mac_val[0])>2) or (len(mac_val[1])>2) or (len(mac_val[2])>2) or (len(mac_val[3])>2) or (len(mac_val[4])>2) or (len(mac_val[5])>2)):
            raise InvalidParameterError(u'Endereco MAC invalido. Formato: FF:FF:FF:FF:FF:FF')


def buscar_id_equip(client, nome):
                
    id_equip = None
    if not nome=='':
            equip = client.create_equipamento().listar_por_nome(nome)
            equip = equip.get('equipamento')
            id_equip = equip['id']
            return (id_equip)


def buscar_nome_equip(client, rack, tipo):
    id_equip = rack.get(tipo)
    if not id_equip==None:
        equip = client.create_equipamento().listar_por_id(id_equip)
        equip = equip.get('equipamento')
        nome_eq =  equip.get('nome')
        rack[tipo] = nome_eq
    else:
        rack[tipo] = ''


def valid_rack_number(rack_number):
   if not rack_number < 120:
      raise InvalidParameterError(u'Numero de Rack invalido. Intervalo valido: 0 - 119') 


def valid_rack_name(rack_name):
   if not check_regex(rack_name, r'^[A-Z][A-Z][0-9][0-9]'):
      raise InvalidParameterError('Nome inváildo. Ex: AA00')


def get_msg(request, var, nome, operation):

    var = var.get('rack_conf')
    var = str(var)

    if var=="True":
        if operation=='CONFIG':
            msg = rack_messages.get('sucess_create_config') % nome 
        elif operation=='ALOCAR':
            msg = rack_messages.get('sucess_alocar_config') % nome
        elif operation=='APLICAR':
            msg = rack_messages.get('sucess_aplicar_config') % nome
        messages.add_message(request, messages.SUCCESS, msg)
    else:
        if operation=='CONFIG':
            msg = rack_messages.get('can_not_create_all') % nome    
        elif operation=='ALOCAR':
            msg = rack_messages.get('can_not_alocar_config') % nome
        elif operation=='APLICAR':
            msg = rack_messages.get('can_not_aplicar_config') % nome
        messages.add_message(request, messages.ERROR, msg)


def rack_config_delete (request, client, form, operation):

        if form.is_valid():

            if operation=='CONFIG':
                id = 'ids_config'
            elif operation == 'DELETE':
                id = 'ids'
            elif operation=='APLICAR':
                id = 'ids_aplicar'
            elif operation=='ALOCAR':
                id = 'ids_alocar'

            # All ids selected
            ids = split_to_array(form.cleaned_data[id])

            # All messages to display
            error_list = list()
            error_list_config = list()
            all_ready_msg_rack_error = False

            # Control others exceptions
            have_errors = False

            # For each rack selected
            for id_rack in ids:
                try:
                    racks = client.create_rack().list()
                    racks = racks.get('rack')
                    for ra in racks:
                        if ra.get('id')==id_rack:
                            rack = ra
                    nome = rack.get('nome')
                    if operation == 'DELETE':
                        msg_sucess = "success_remove"
                        client.create_rack().remover(id_rack)
                    elif operation == 'CONFIG':
                        var = client.create_rack().gerar_arq_config(id_rack)
                        var = var.get('sucesso')
                        get_msg(request, var, nome, operation)
                    elif operation=='APLICAR':
                        var = client.create_apirack().rack_deploy(id_rack)
                        var = var.get('sucesso')
                        get_msg(request, var, nome, 'APLICAR')
                    elif operation=='ALOCAR':
                        var = client.create_rack().alocar_configuracao(id_rack)
                        var = var.get('sucesso')
                        get_msg(request, var, nome, operation)
                except RackAllreadyConfigError, e:
                    logger.error(e)
                    error_list_config.append(id_rack)
                except RacksError, e:
                    logger.error(e)
                    if not all_ready_msg_rack_error:
                        messages.add_message(request, messages.ERROR, e)
                    all_ready_msg_rack_error = True
                    error_list.append(id_rack)
                except NetworkAPIClientError, e:
                    logger.error(e)
                    messages.add_message(request, messages.ERROR, e)
                    have_errors = True
                    break

            if len(error_list_config) > 0:

                msg = ""
                for id_error in error_list_config:
                    msg = msg + id_error + ','

                messages.add_message(request, messages.WARNING, msg)
                have_errors = True

            if len(error_list) == len(ids):
                messages.add_message(
                    request, messages.ERROR, error_messages.get("can_not_remove_all"))

            elif len(error_list) > 0:
                msg = ""
                for id_error in error_list:
                    msg = msg + id_error + ", "

                msg = error_messages.get("can_not_remove") % msg[:-2]

                messages.add_message(request, messages.WARNING, msg)

            elif (not operation=='CONFIG') and (not operation=='ALOCAR') and (not operation=='APLICAR') and (have_errors == False):
                messages.add_message(request, messages.SUCCESS, rack_messages.get(msg_sucess))

            return redirect("ajax.view.rack")

        else:
            messages.add_message(request, messages.ERROR, error_messages.get("select_one"))

         # Redirect to list_all action
        return redirect("ajax.view.rack")


@log
@login_required
@has_perm([{"permission": EQUIPMENT_MANAGEMENT, "write": True}, ])
def rack_form(request):
   
    try:

        lists = dict()
        auth = AuthSession(request.session)
        client = auth.get_clientFactory()

        form = RackForm()

        if request.method == 'GET':

            racks = client.create_rack().list()
            numero = proximo_rack(racks)
            form = RackForm(initial={'rack_number': numero})

        if request.method == 'POST':

            form = RackForm(request.POST)
            if form.is_valid():
                rack_number = form.cleaned_data['rack_number']
                rack_name = form.cleaned_data['rack_name']
                mac_sw1 = form.cleaned_data['mac_address_sw1']
                mac_sw2 = form.cleaned_data['mac_address_sw2']
                mac_ilo = form.cleaned_data['mac_address_ilo']
                nome_sw1 = form.cleaned_data['nome_sw1']
                nome_sw2 = form.cleaned_data['nome_sw2']
                nome_ilo = form.cleaned_data['nome_ilo']

                # validacao: Numero do Rack
                valid_rack_number(rack_number)
 
                # validacao: Nome do Rack
                valid_rack_name(rack_name)

                # Validacao: MAC 
                validar_mac(mac_sw1)
                validar_mac(mac_sw2)
                validar_mac(mac_ilo)
                
                id_sw1 = buscar_id_equip(client,nome_sw1)
                id_sw2 = buscar_id_equip(client,nome_sw2)
                id_ilo = buscar_id_equip(client,nome_ilo)
 
                rack = client.create_apirack().insert_rack(rack_number, rack_name, mac_sw1, mac_sw2, mac_ilo, id_sw1, id_sw2, id_ilo)
                messages.add_message(request, messages.SUCCESS, rack_messages.get("success_insert"))

                form = RackForm()
                return redirect('ajax.view.rack')

    except NetworkAPIClientError, e:
        logger.error(e)
        messages.add_message(request, messages.ERROR, e)
    return render_to_response(RACK_FORM, {'form': form}, context_instance=RequestContext(request))


@log
@login_required
@has_perm([{"permission": EQUIPMENT_MANAGEMENT, "read": True}, {"permission": EQUIPMENT_MANAGEMENT, "write": True}])
def ajax_view(request):

    # Get user
    auth = AuthSession(request.session)
    client_api = auth.get_clientFactory()

    return ajax_rack_view(request, client_api)


def ajax_rack_view(request, client_api):

    try:

        racks = dict()

        # Get all racks from NetworkAPI
        racks = client_api.create_rack().list()

        if not racks.has_key("rack"):
                    racks["rack"] = []

        rack = racks.get('rack')

        for var in rack:
            mac_1 = var.get("mac_sw1")           
            mac_2 = var.get("mac_sw2")           
            mac_3 = var.get("mac_ilo")
           
            buscar_nome_equip(client_api, var, 'id_sw1')
            buscar_nome_equip(client_api, var, 'id_sw2')
            buscar_nome_equip(client_api, var, 'id_ilo')

            if mac_1==None:
                var['mac_sw1'] = ''
            if mac_2==None:
                var['mac_sw2'] = ''
            if mac_3==None:
                var['mac_ilo'] = ''

            var['config'] = var.get("config")

            if var.get("rack_vlan_amb")=='True':
                var['rack_vlan_amb'] = "True"
            else:
                var['rack_vlan_amb'] = "False"

        racks['delete_form'] = DeleteForm()
        racks['config_form'] = ConfigForm()
        racks['aplicar_form'] = AplicarForm()
        racks['criar_vlan_amb_form'] = CriarVlanAmbForm()
        racks['alocar_form'] = AlocarForm()


    except NetworkAPIClientError, e:
        logger.error(e)
        messages.add_message(request, messages.ERROR, e)

    return render_to_response(RACK_VIEW_AJAX, racks, context_instance=RequestContext(request))


@log
@login_required
@has_perm([{"permission": EQUIPMENT_MANAGEMENT, "write": True}, ])
def rack_edit(request, id_rack):

    lists = dict()
    lists['id'] = id_rack

    try:
        auth = AuthSession(request.session)
        client = auth.get_clientFactory()

        # Get all racks from NetworkAPI
        racks = client.create_rack().list()

        if not racks.has_key("rack"):
                    racks["rack"] = []

        rackn = racks.get('rack')
        for var in rackn:
            if (var['id']==id_rack):
                rack = var

        if request.method == 'GET':
            try:
                rack_num = rack.get('numero')
                rack_name = rack.get('nome')
            except:
                rack_num = None
                pass
            lists['numero'] = rack_num
            try:
                nome_sw1 = client.create_equipamento().listar_por_id(rack.get('id_sw1'))['equipamento']['nome']
                mac_sw1 = rack.get('mac_sw1')
            except:
                nome_sw1 = None
                mac_sw1 = None
                pass
            try:
                nome_sw2 = client.create_equipamento().listar_por_id(rack.get('id_sw2'))['equipamento']['nome']
                mac_sw2 = rack.get("mac_sw2")
            except:
                nome_sw2 = None
                mac_sw2 = None
                pass
            try:
                nome_ilo = client.create_equipamento().listar_por_id(rack.get('id_ilo'))['equipamento']['nome']
                mac_ilo = rack.get('mac_ilo')
            except:
                nome_ilo = None
                mac_ilo = None
                pass
            lists['form'] = RackForm(initial={'rack_number': rack_num, 'rack_name': rack_name, "nome_sw1": nome_sw1,
                                              'mac_address_sw1': mac_sw1, 'mac_address_sw2': mac_sw2, 'nome_sw2': nome_sw2,
                                              'mac_address_ilo': mac_ilo, 'nome_ilo': nome_ilo})
    
        if request.method == 'POST':
            form = RackForm(request.POST)
            lists['form'] = form

            if form.is_valid():
                numero = form.cleaned_data['rack_number']
                nome = form.cleaned_data['rack_name']
                mac_sw1 = form.cleaned_data['mac_address_sw1']
                mac_sw2 = form.cleaned_data['mac_address_sw2']
                mac_ilo = form.cleaned_data['mac_address_ilo']
                nome_sw1 = form.cleaned_data['nome_sw1']
                nome_sw2 = form.cleaned_data['nome_sw2']
                nome_ilo = form.cleaned_data['nome_ilo']

                # Validacao: MAC 
                validar_mac(mac_sw1)
                validar_mac(mac_sw2)
                validar_mac(mac_ilo)

                id_sw1 = buscar_id_equip(client,nome_sw1)
                id_sw2 = buscar_id_equip(client,nome_sw2)
                id_ilo = buscar_id_equip(client,nome_ilo)

                rack = client.create_rack().edit_rack(id_rack, numero, nome, mac_sw1, mac_sw2, mac_ilo, id_sw1, id_sw2, id_ilo)
                messages.add_message(request, messages.SUCCESS, rack_messages.get("success_edit"))

                return redirect('ajax.view.rack')

    except NetworkAPIClientError, e:
        logger.error(e)
        messages.add_message(request, messages.ERROR, e)

    return render_to_response(RACK_EDIT, lists, context_instance=RequestContext(request))


@log
@login_required
@has_perm([{"permission": EQUIPMENT_MANAGEMENT, "write": True}])
def rack_config (request):

    if request.method == 'POST':

        form = ConfigForm(request.POST)
       
        auth = AuthSession(request.session)
        client = auth.get_clientFactory()

        rack_config_delete(request, client, form, 'CONFIG')

    return redirect("ajax.view.rack")


@log
@login_required
@has_perm([{"permission": EQUIPMENT_MANAGEMENT, "write": True}])
def rack_delete (request):

    if request.method == 'POST':
        
        form = DeleteForm(request.POST)

        auth = AuthSession(request.session)
        client = auth.get_clientFactory()

        rack_config_delete(request, client, form, 'DELETE')

    return redirect("ajax.view.rack")


@log
@login_required
@has_perm([{"permission": EQUIPMENT_MANAGEMENT, "write": True}])
def rack_alocar(request):

    if request.method == 'POST':

        form = AlocarForm(request.POST)

        auth = AuthSession(request.session)
        client = auth.get_clientFactory()

        rack_config_delete(request, client, form, 'ALOCAR')

    return redirect("ajax.view.rack")


@log
@login_required
@has_perm([{"permission": EQUIPMENT_MANAGEMENT, "write": True}])
def rack_deploy(request):

    if request.method == 'POST':

        form = AplicarForm(request.POST)

        auth = AuthSession(request.session)
        client = auth.get_clientFactory()

        rack_config_delete(request, client, form, 'APLICAR')

    return redirect("ajax.view.rack")


# ################################################################################   DC
def menu(request):
    return render_to_response(MENU, {'form': {}}, context_instance=RequestContext(request))


@log
@login_required
@has_perm([{"permission": EQUIPMENT_MANAGEMENT, "write": True}, ])
@csrf_protect
def new_datacenter(request):

    try:

        auth = AuthSession(request.session)
        client = auth.get_clientFactory()

        if request.method == 'POST':

            dc = dict()
            dc['dcname'] = request.POST.get('name')
            dc['address'] = request.POST.get('address')

            newdc = client.create_apirack().save_dc(dc)
            id = newdc.get('dc').get('id')

            return HttpResponseRedirect(reverse('fabric.cadastro', args=[id]))

    except NetworkAPIClientError, e:
        logger.error(e)
        messages.add_message(request, messages.ERROR, e)
    return render_to_response(DC_FORM, {'form': {}}, context_instance=RequestContext(request))


@log
@login_required
@has_perm([{"permission": EQUIPMENT_MANAGEMENT, "write": True}, ])
@csrf_protect
def new_fabric(request, dc_id):

    try:

        auth = AuthSession(request.session)
        client = auth.get_clientFactory()

        lists = dict()
        lists['dc_id'] = dc_id
        lists["action"] = reverse('fabric.cadastro', args=[dc_id])

        if request.method == 'POST':

            fabric = dict()
            fabric['dc'] = request.META.get('HTTP_REFERER').split("/")[-1]
            fabric['name'] = request.POST.get('fabricname')
            fabric['racks'] = request.POST.get('spn')
            fabric['spines'] = request.POST.get('rack')
            fabric['leafs'] = request.POST.get('lfs')

            newfabric = client.create_apirack().save_fabric(fabric)
            dc_id = newfabric.get('dcroom').get('id')
            lists["dc_id"] = dc_id

            return HttpResponseRedirect(reverse('fabric.ambiente', args=[dc_id]))

    except NetworkAPIClientError, e:
        logger.error(e)
        messages.add_message(request, messages.ERROR, e)
    return render_to_response(DCROOM_FORM, lists, context_instance=RequestContext(request))


@log
@login_required
@has_perm([{"permission": EQUIPMENT_MANAGEMENT, "write": True}, ])
@csrf_protect
def fabric_ambiente(request, fabric_id):

    try:

        auth = AuthSession(request.session)
        client = auth.get_clientFactory()

        lists = dict()
        lists['fabric_id'] = fabric_id
        lists["action"] = reverse('fabric.ambiente', args=[fabric_id])

        lists["net_type_list"] = client.create_tipo_rede().listar().get("net_type")
        lists["env_logic"] = client.create_ambiente_logico().listar().get("logical_environment")
        lists["env_dc"] = client.create_divisao_dc().listar().get("division_dc")
        lists["env_l3"] = client.create_grupo_l3().listar().get("group_l3")
        lists["filters"] = client.create_filter().list_all().get("filter")
        lists["envs"] = client.create_ambiente().listar().get('ambiente')
        vrfs = client.create_api_vrf().search()['vrfs']
        lists["vrfs"] = sorted(vrfs, key=operator.itemgetter('vrf'))

        """
        try:
            templates = acl.get_templates(auth.get_user(), True)
        except GITCommandError, e:
            logger.error(e)
            messages.add_message(request, messages.ERROR, e)
            templates = {
                'ipv4': list(),
                'ipv6': list()
            }
        lists["ipv4"] = templates.get("ipv4")
        lists["ipv6"] = templates.get("ipv6")
        """
        if request.method == 'POST':
            url = request.META.get('HTTP_REFERER').split("/")
            fabric_id = url[-1] if url[-1] else url[-2]
            lists["fabric_id"] = fabric_id

            vrf = ast.literal_eval(request.POST.get('select_vrf'))

            configs = list()

            if request.POST.get('ipv4range'):
                config = {
                    'subnet': request.POST.get('ipv4range'),
                    'new_prefix': request.POST.get('prefixv4'),
                    'type': "v4",
                    'network_type': int(request.POST.get('env_type')),
                }
                configs.append(config)
            if request.POST.get('ipv6range'):
                config = {
                    'subnet': request.POST.get('ipv6range'),
                    'new_prefix': request.POST.get('prefixv6'),
                    'type': "v6",
                    'network_type': int(request.POST.get('env_type')),
                }
                configs.append(config)

            env_dict = {
                "id": None,
                "fabric_id": int(fabric_id),
                "grupo_l3": int(request.POST.get('select_env_l3')),
                "ambiente_logico": int(request.POST.get('select_env_log')),
                "divisao_dc": int(request.POST.get('select_divisaodc')),
                "filter": int(request.POST.get('select_filter')) if request.POST.get('select_filter') else None,
                "acl_path": request.POST.get('envpathacl', None),
                "ipv4_template": request.POST.get('envtemplateaclv4', None),
                "ipv6_template": request.POST.get('envtemplateaclv6', None),
                "link": None,
                "min_num_vlan_1": int(request.POST.get('vlanmin')) if request.POST.get('vlanmin') else None,
                "max_num_vlan_1": int(request.POST.get('vlanmax')) if request.POST.get('vlanmax') else None,
                "min_num_vlan_2": None,
                "max_num_vlan_2": None,
                "default_vrf": int(vrf.get("id")) if vrf.get("id") else None,
                'vrf': vrf.get('vrf', ''),
                "father_environment": None,
                "configs": configs
            }
            environment = client.create_api_environment().create_environment(env_dict)
            messages.add_message(request, messages.SUCCESS, environment_messages.get("success_insert"))

            # if mais prefixo
            # redireciona para outra pagina para inserir os ambientes filhos

            return HttpResponseRedirect(reverse('fabric.ambiente', args=[fabric_id]))

    except NetworkAPIClientError, e:
        logger.error(e)
        messages.add_message(request, messages.ERROR, e)
    return render_to_response(DCROOM_ENV_FORM, lists, context_instance=RequestContext(request))


@log
@login_required
@has_perm([{"permission": EQUIPMENT_MANAGEMENT, "write": True}, ])
@csrf_protect
def fabric_bgp(request, fabric_id):

    try:

        auth = AuthSession(request.session)
        client = auth.get_clientFactory()

        lists = dict()
        lists['fabric_id'] = fabric_id
        lists["action"] = reverse('fabric.bgp', args=[fabric_id])


        if request.method == 'POST':
            lists["fabric_id"] = fabric_id

            bgp = {
                'mpls': request.POST.get('fabricasnmpls'),
                'spines': request.POST.get('fabricasnspn'),
                'leafs': request.POST.get('fabricasnlfs')
            }
            vlt = {
                'id_vlt_lf1': request.POST.get('fabricvlt01'),
                'priority_vlt_lf1': request.POST.get('fabricpriority01'),
                'id_vlt_lf2': request.POST.get('fabricvlt02'),
                'priority_vlt_lf2': request.POST.get('fabricpriority02')
            }
            telecom = {
                'rede': request.POST.get('gerenciatelecom'),
                'vlan': request.POST.get('gerenciavlan')
            }
            monitoracao = {
                'rede': request.POST.get('gerenciamonitoracao'),
                'vlan': request.POST.get('gerenciamonitvlan')
            }
            noc = {
                'rede': request.POST.get('gerencianoc'),
                'vlan': request.POST.get('gerencianocvlan')
            }

            gerencia = dict()
            gerencia["telecom"] = telecom
            gerencia["monitoracao"] = monitoracao
            gerencia["noc"] = noc

            config = dict()
            config["BGP"] = bgp
            config["Gerencia"] = gerencia
            config["VLT"] = vlt
            config["flag"] = True

            environment = client.create_apirack().edit_fabric(fabric_id, config)

            return render_to_response(DCROOM_BGP_FORM, lists, context_instance=RequestContext(request))

    except NetworkAPIClientError, e:
        logger.error(e)
        messages.add_message(request, messages.ERROR, e)
    return render_to_response(DCROOM_BGP_FORM, lists, context_instance=RequestContext(request))