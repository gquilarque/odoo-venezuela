#!/usr/bin/python
# -*- encoding: utf-8 -*-
###########################################################################
#    Module Writen to OpenERP, Open Source Management Solution
#    Copyright (C) OpenERP Venezuela (<http://openerp.com.ve>).
#    All Rights Reserved
###############Credits######################################################
#    Coded by: Humberto Arocha           <humberto@openerp.com.ve>
#              Maria Gabriela Quilarque  <gabrielaquilarque97@gmail.com>
#    Planified by: Nhomar Hernandez
#    Finance by: Helados Gilda, C.A. http://heladosgilda.com.ve
#    Audited by: Humberto Arocha humberto@openerp.com.ve
#############################################################################
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
##############################################################################
from osv import osv
from osv import fields
from tools.translate import _
from tools import config
import time
import datetime

class account_invoice_line(osv.osv):
    '''
    Se agrega un campo donde se determina, si una linea ha sido retenida o no.
    '''
    _inherit = "account.invoice.line"

    _columns = {
        'apply_wh': fields.boolean('Retenido',help="Indica si una linea ha sido retenida o no, para ir acumulando el monto a retener el proximo mes, de acuerdo a las lineas que no han sido retenidas."),
        'concept_id': fields.many2one('islr.wh.concept','Concepto de Retencion',help="Concepto de Retencion asociado a esta Tasa",required=False),
    }
    _defaults = {
        'apply_wh': lambda *a: False,
    }
    
    def product_id_change(self, cr, uid, ids, product, uom, qty=0, name='', type='out_invoice', partner_id=False, fposition_id=False, price_unit=False, address_invoice_id=False, context=None):
        '''
        onchange para que aparezca el concepto de retencion asociado al producto de una vez en la linea de la factura
        '''
        data = super(account_invoice_line, self).product_id_change(cr, uid, ids, product, uom, qty, name, type, partner_id, fposition_id, price_unit, address_invoice_id, context)
        pro = self.pool.get('product.product').browse(cr, uid, product, context=context)
        concepto=pro.concept_id.id
        data[data.keys()[1]]['concept_id'] = concepto
        return data
        

####NO SIRVE EL COPY
    def copy(self, cr, uid, id, default=None, context=None):
        if default is None:
            default = {}
        default = default.copy()
        default.update({'apply_wh':False})
        
        return super(account_invoice_line, self).copy(cr, uid, id, default, context)

account_invoice_line()


class account_invoice(osv.osv):

    _inherit = 'account.invoice'
    
    def _get_partners(self, cr, uid, invoice):
        if invoice.type == 'in_invoice' or invoice.type == 'in_refund':
            vendor = invoice.partner_id
            buyer = invoice.company_id.partner_id
        else:
            buyer = invoice.partner_id
            vendor = invoice.company_id.partner_id
        return (vendor, buyer, buyer.islr_withholding_agent)

    def _get_concepts(self, cr, uid, invoice):
        '''
        Se obtienen una lista de concept_id, de las lineas en la factura
        '''
        service_list = []
        for invoice_line in invoice.invoice_line:
            if invoice_line.concept_id and invoice_line.concept_id.withholdable:
                service_list.append(invoice_line.concept_id.id)
            else:
                return False
        return list(set(service_list))
        

    def _get_service_wh(self, cr, uid, invoice, concept_list):
        '''
        Obtiene las lineas de factura de este partner en el periodo de esta factura
        '''
        dict={}
        for key in concept_list:
            dict[key]={'lines':[],'wh':False,'base':0.0}
        inv_obj = self.pool.get('account.invoice')
        inv_lst = inv_obj.search(cr, uid,[('partner_id', '=', invoice.partner_id.id),('period_id','=',invoice.period_id.id),('state','in',['done','open'])])
        
        inv_line_lst=[]
        for id in inv_lst:
            inv_line_brw = inv_obj.browse(cr, uid, id).invoice_line
            for line in inv_line_brw:
                if line.concept_id and  line.concept_id.id in concept_list:
                    if not line.apply_wh:
                        dict[line.concept_id.id]['lines'].append(line.id)
                        dict[line.concept_id.id]['base']+= line.price_subtotal
                    else:
                        dict[line.concept_id.id]['wh']=True
        #~ dict[key]={'lines':[],'wh':False,'base':0.0}
        return dict

    def _get_country_fiscal(self,cr, uid, partner_id):
        for i in partner_id.address:
            if i.type=='invoice':
                if not i.country_id:
                    raise osv.except_osv(_('Invalid action !'),_("Imposible realizar Comprobante de Retencion ISLR, debido a que el partner'%s' no tiene pais en su facturacion fiscal!") % (partner_id.name))
                    return False
                else:
                    return i.country_id.id
            else:
                raise osv.except_osv(_('Invalid action !'),_("Imposible realizar Comprobante de Retencion ISLR, debido a que el partner'%s' no tiene direccion fiscal asociada!") % (partner_id.name))
                return False
        return False
                

    def _get_residence(self, cr, uid, vendor, buyer):
        vendor_address = self._get_country_fiscal(cr, uid, vendor)
        buyer_address = self._get_country_fiscal(cr, uid, buyer)
        if vendor_address and buyer_address:
            if vendor_address ==  buyer_address:
                return True
            else:
                return False
        return False

    def _get_nature(self, cr, uid, partner_id):
        if not partner_id.vat:
            raise osv.except_osv(_('Invalid action !'),_("Imposible realizar Comprobante de Retencion ISLR, debido a que el partner, '%s' no tiene RIF asociado!") % (partner_id.name))
            return False
        else:
            if partner_id.vat[2:3] in 'VvEe':
                return True
            else:
                return False

    def _get_rate(self, cr, uid, concept_id, residence, nature):
        rate_brw_lst = self.pool.get('islr.wh.concept').browse(cr, uid, concept_id).rate_ids
        for rate_brw in rate_brw_lst:
            if rate_brw.nature == nature and rate_brw.residence == residence:
                #~ (base,min,porc,sust,codigo,id_rate,name_rate)
                ####AQUI HAGO LA CUESTION, CUANDO HAY DOS PERC Y COMPARO
                return (rate_brw.base, rate_brw.minimum, rate_brw.wh_perc, rate_brw.subtract,rate_brw.code,rate_brw.id,rate_brw.name)
        return ()
    
    def _get_rate_dict(self, cr, uid, concept_list, residence, nature):
        dict = {}
        cont = 0
        for concept_id in concept_list:
            dict[concept_id] = self._get_rate(cr, uid, concept_id, residence, nature)
            if dict[concept_id]:
                cont += 1
        if not cont:
            raise osv.except_osv(_('Invalid action !'),_("Imposible realizar Comprobante de Retencion ISLR, debido a que  el Concepto de Retencion asociado a la linea no es de tipo Retenible!"))
        return dict


    def _pop_dict(self,cr,uid,concept_list,dict_rate,wh_dict):
        for concept in concept_list:
            if not dict_rate[concept]:
                dict_rate.pop(concept)
                wh_dict.pop(concept)


    def _get_wh_calc(self,cr,uid,line,dict_rate_concept):
        base = self.pool.get('account.invoice.line').browse(cr,uid,line).price_subtotal
        return (base * (dict_rate_concept[0]/100) * (dict_rate_concept[2]/100), base)


    def _get_number(self,cr,uid,number,long):
        num1 = number[::-1]
        result= ''
        for i in num1:
            if i.isdigit():
                if len(result)<long:
                    result = i + result
                else:
                    break
            else:
                break
        return result.strip()


    def _get_inv_data(self,cr, uid, line):
        inv_brw = self.pool.get('account.invoice.line').browse(cr, uid, line).invoice_id
        vat = inv_brw.partner_id.vat[2:]
        if inv_brw.type == 'in_invoice' or inv_brw.type == 'in_refund':
            number = inv_brw.reference.strip()

            if not inv_brw.reference:
                number = 0
            else:
                number = self._get_number(cr,uid,inv_brw.reference.strip(),10)
        else:
            if not inv_brw.number:
                number = 0
            else:
                number = self._get_number(cr,uid,inv_brw.number.strip(),10)

        if not inv_brw.nro_ctrl:
            raise osv.except_osv(_('Invalid action !'),_("Imposible realizar Comprobante de Retencion ISLR, debido a que la factura no tiene Numero de Control Asociado!"))
        else:
            control = self._get_number(cr,uid,inv_brw.nro_ctrl.strip(),8)
        return (vat, number, control)


    def _write_wh_apply(self,cr, uid,line,dict,apply):
        il_ids = self.pool.get('account.invoice.line').browse(cr, uid,line)
        
        if il_ids.wh_xml_id:
            self.pool.get('account.invoice.line').write(cr, uid, line, {'apply_wh': apply})
            self.pool.get('islr.xml.wh.line').write(cr,uid,il_ids.wh_xml_id.id,{'wh':dict['wh']})
        else:
            self.pool.get('account.invoice.line').write(cr, uid, line, {'apply_wh': apply,'wh_xml_id':self._create_islr_xml_wh_line(cr, uid,line,dict)})
    
    def _create_islr_xml_wh_line(self,cr, uid, line, dict):
        inv_id = self.pool.get('account.invoice.line').browse(cr, uid,line).invoice_id
        
        return self.pool.get('islr.xml.wh.line').create(cr, uid, {'name': dict['name_rate'],
        'concept_id': dict['concept'], 
        'period_id':  inv_id.period_id.id,
        'partner_vat':dict['vat'],
        'invoice_number': dict['number'],
        'control_number': dict['control'],
        'concept_code':dict['code'],
        'base': dict['subtotal'],
        'porcent_rete':dict['perc'],
        'wh':dict['wh'],
        'rate_id': dict['rate_id'],
        'account_invoice_line_id': line,
        'partner_id': inv_id.partner_id.id,
        })

    def _get_wh(self,cr, uid, subtract,concept, wh_dict, dict_rate, apply):
        res= {}
        if apply:
            for line in wh_dict[concept]['lines']:
                wh_calc, subtotal = self._get_wh_calc(cr,uid,line,dict_rate[concept])
                if subtract >= wh_calc:
                    wh = 0.0
                    subtract -= wh_calc
                else:
                    wh = wh_calc - subtract
                    subtract=0.0
                res[line]={ 'vat': self._get_inv_data(cr, uid, line)[0],
                            'number': self._get_inv_data(cr, uid, line)[1],
                            'control': self._get_inv_data(cr, uid, line)[2],
                            'concept': concept, 
                            'code':dict_rate[concept][4],
                            'subtotal': subtotal, 
                            'perc':dict_rate[concept][2],
                            'wh':wh,
                            'apply':apply,
                            'rate_id':dict_rate[concept][5],
                            'name_rate': dict_rate[concept][6]}
                self._write_wh_apply(cr,uid,line,res[line],apply)
            return res
        else: # no aplica
            for line in wh_dict[concept]['lines']:
                subtotal = self._get_wh_calc(cr,uid,line,dict_rate[concept])[1]
                res[line]={ 'vat': self._get_inv_data(cr, uid, line)[0],
                            'number': self._get_inv_data(cr, uid, line)[1],
                            'control': self._get_inv_data(cr, uid, line)[2],
                            'concept': concept, 
                            'code':dict_rate[concept][4],
                            'subtotal': subtotal, 
                            'perc':dict_rate[concept][2],
                            'wh':0.0,
                            'apply':apply,
                            'rate_id':dict_rate[concept][5],
                            'name_rate': dict_rate[concept][6]}
                self._write_wh_apply(cr,uid,line,res[line],apply)
            return res


    def _get_wh_apply(self,cr,uid,dict_rate,wh_dict):
        res = {}
        for concept in wh_dict:
            if not wh_dict[concept]['wh']:
                if wh_dict[concept]['base'] >= dict_rate[concept][1]:
                    subtract = dict_rate[concept][3]
                    res.update(self._get_wh(cr, uid, subtract,concept, wh_dict, dict_rate, True))
                else:
                    subtract = 0.0
                    res.update(self._get_wh(cr, uid, subtract,concept, wh_dict, dict_rate, False))
            else: #se aplica rete de una vez, sobre la base.
                subtract = 0.0
                res.update(self._get_wh(cr, uid, subtract,concept, wh_dict, dict_rate, True))
        return res


    def _get_amount(self,cr,uid,dict):
        '''
        Funcion para obtener, la suma del monto retenido por concepto.
        '''
        dict_concept = {}
        for key in dict:
            x = dict[key]['concept']
            y = dict[key]['wh']
            if not dict_concept.get(x,False):
                dict_concept[x] = y
            else:
                dict_concept[x]+= y
        return dict_concept


    def _get_dict_concepts(self,cr,uid,dict):
        '''
        Funcion para obtener, el dicccionario agrupado por concepto:  
        {1:[{64: {'control': '', 'perc': 0.050000000000000003, 'concept': 1, 'number': False, 'wh': 0.0, 'code': u'A', 'rate_id': 1, 'apply': True, 'subtotal': 500.0, 'vat': u'J123456789'}}, 
            {65: {'control': '', 'perc': 0.050000000000000003, 'concept': 1, 'number': False, 'wh': 0.0, 'code': u'A', 'rate_id': 1, 'apply': True, 'subtotal': 300.0, 'vat': u'J123456789'}}
           ], 
         2:[{63: {'control': '', 'perc': 0.029999999999999999, 'concept': 2, 'number': False, 'wh': 0.0, 'code': u'002', 'rate_id': 2, 'apply': True, 'subtotal': 1000.0, 'vat': u'J123456789'}}
            ]}
        '''
        dict_concepts = {}
        for key in dict:
            x = dict[key]['concept']
            y = dict[key]
            if not dict_concepts.get(x,False):
                if dict[key]['apply']:
                    dict_concepts[x]=[]
                    dict_concepts[x].append({key:y})
            else:
                if dict[key]['apply']:
                    dict_concepts[x].append({key:y})
        return dict_concepts


    def _create_islr_wh_doc(self,cr,uid,inv_brw,dict):
        '''
        Funcion para crear en el modelo islr_wh_doc
        '''
        islr_wh_doc_id=0 
        wh_doc_obj = self.pool.get('islr.wh.doc')
        inv_obj =self.pool.get('account.invoice.line')
        inv_brw = inv_brw.invoice_id
        
        islr_wh_doc_id = wh_doc_obj.create(cr,uid,{'name':'HOLA HUMBELLLTO',
                                                   'partner_id': inv_brw.partner_id.id,
                                                   'invoice_id': inv_brw.id,
                                                   'period_id': inv_brw.period_id.id})
        return islr_wh_doc_id


    def _create_doc_line(self,cr,uid, inv_brw,key2,islr_wh_doc_id,dict,dictc):
        '''
        Funcion para crear en el modelo islr_wh_doc_line
        '''
        doc_line_obj = self.pool.get('islr.wh.doc.line')
        rate_obj = self.pool.get('islr.rates')
        dict_concept = self._get_amount(cr,uid,dict)
        inv_line_id = dictc[key2][0].keys()[0]
        rate_id = dictc[key2][0][inv_line_id]['rate_id']
        
        
        line_idd = dictc[key2][0]
        print 'LINEEEE IDDD', line_idd
        
        inv_idd = self.pool.get('account.invoice').browse(cr,uid,line_idd).invoice_id
        print 'IDDDD INVOICEEEE', inv_idd
        
        
        islr_wh_doc_line_id = doc_line_obj.create(cr,uid,{'islr_wh_doc_id':islr_wh_doc_id,
                                                'concept_id':key2,
                                                'islr_rates_id':rate_id,
                                                'invoice_id': inv_brw.invoice_id.id,
                                                'retencion_islr': rate_obj.browse(cr,uid,rate_id).wh_perc,
                                                'amount':dict_concept[key2]
                                                })
        return islr_wh_doc_line_id


    def _create_doc_invoices(self,cr,uid,key,islr_wh_doc_id):
        '''
        Funcion para crear en el modelo islr_wh_doc_invoices
        '''
        doc_inv_obj = self.pool.get('islr.wh.doc.invoices')
        inv_id = key
        islr_wh_doc_invoices_id = doc_inv_obj.create(cr,uid,{'invoice_id':inv_id,'islr_wh_doc_id':islr_wh_doc_id})


    def _write_wh_xml(self,cr,uid,key,islr_wh_doc_line_id):
        '''
        Funcion para escribir en el modelo xml_wh_line
        '''
        inv_obj =self.pool.get('account.invoice.line')
        xml_obj = self.pool.get('islr.xml.wh.line')
        xml_id = inv_obj.browse(cr,uid,key).wh_xml_id.id
        xml_obj.write(cr, uid, xml_id, {'islr_wh_doc_line_id':islr_wh_doc_line_id})


    def _get_inv_id(self,cr,uid,dict):
        '''
        Funcion para obtener el objeto_browse de la factura
        '''
        inv_brw = False
        inv_obj =self.pool.get('account.invoice.line')
        line_ids = []
        inv_id1 = 0
        for key in dict:
            if dict[key]['apply']:
                line_ids.append(key)
        if line_ids:
            line_ids.sort()
            inv_id1 = line_ids[-1]
            inv_brw = inv_obj.browse(cr,uid,inv_id1)
        return inv_brw


    def _logic_create(self,cr,uid,dict):
        '''
        Manejo de toda la logica para la generarion de lineas en los modelos.
        '''
        dictc = self._get_dict_concepts(cr,uid,dict)
        inv_brw = self._get_inv_id(cr,uid,dict)
        inv_obj =self.pool.get('account.invoice.line')
        
        if inv_brw:
            if dictc:
                islr_wh_doc_id = self._create_islr_wh_doc(cr,uid,inv_brw,dict)
            else:
                pass
            key_lst = []
            if islr_wh_doc_id:
                for key2 in dictc:
                    inv_line_id = dictc[key2][0].keys()[0]
                    islr_wh_doc_line_id = self._create_doc_line(cr,uid,inv_brw,key2,islr_wh_doc_id,dict,dictc)
                    for line in dictc[key2]:
                        inv_line_id2 = dictc[key2][0].keys()[0]
                        for key in line:
                            key_lst.append(inv_obj.browse(cr,uid,key).invoice_id.id)
                            self._write_wh_xml(cr,uid,key,islr_wh_doc_line_id)
                for key in set(key_lst):
                    self._create_doc_invoices(cr,uid,key,islr_wh_doc_id)
                        
                        
                self.pool.get('account.invoice').write(cr,uid,inv_brw.invoice_id.id,{'islr_wh_doc_id':islr_wh_doc_id})
            else:
                pass
        else:
            pass

    def action_ret_islr(self, cr, uid, ids, context={}):
        invoices_brw = self.browse(cr, uid, ids, context=None)
        wh_doc_list = []
        for invoice in invoices_brw:
            wh_doc_list = self.pool.get('islr.wh.doc.invoices').search(cr,uid,[('invoice_id','=',invoice.id)])
            if wh_doc_list:
                raise osv.except_osv(_('Invalid action !'),_("La Retencion a la factura '%s' ya fue realizada!") % (invoice.number))
            else:
                wh_dict={}
                dict_rate={}
                dict_completo={}
                vendor, buyer, apply_wh = self._get_partners(cr,uid,invoice)
                concept_list = self._get_concepts(cr,uid,invoice)
                if concept_list:
                    if apply_wh:
                        wh_dict = self._get_service_wh(cr, uid, invoice, concept_list)
                        residence = self._get_residence(cr, uid, vendor, buyer)
                        nature = self._get_nature(cr, uid, vendor)
                        dict_rate = self._get_rate_dict(cr, uid, concept_list, residence, nature)
                        self._pop_dict(cr,uid,concept_list,dict_rate,wh_dict)
                        dict_completo = self._get_wh_apply(cr,uid,dict_rate,wh_dict)
                        print 'FINALLL:: ', dict_completo
                        self._logic_create(cr,uid,dict_completo)
                    else:
                        raise osv.except_osv(_('Invalid action !'),_("Imposible realizar Comprobante de Retencion ISLR, debido a que el comprador '%s' no es agente de Retencion!") % (buyer.name))
                else:
                    raise osv.except_osv(_('Invalid action !'),_("Imposible realizar Comprobante de Retencion ISLR, debido a que las lineas de la factura no tienen Concepto de Retencion!"))
account_invoice()
