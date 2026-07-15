/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { CogMenu } from "@web/search/cog_menu/cog_menu";
import { useState } from "@odoo/owl"; 

patch(CogMenu.prototype, {
    setup() {  
        super.setup();
        this.access = useState({removeSpreadsheet: false}); 
    },
    async checkAvailbility(){
        var self = this; 
        if(this?.env?.config?.actionType == "ir.actions.act_window") { 
            await this.orm.call(
                "access.management",
                "is_spread_sheet_available",
                [1, this?.env?.config?.actionType, this?.env?.config?.actionId]
            ).then(async function(res){
                self.access.removeSpreadsheet = res; 
            })
        } 
    },
    async _registryItems() { 
        await this.checkAvailbility();
        var res = await super._registryItems();
        if(this.access.removeSpreadsheet){
            res = res.filter((i)=>i.key != 'SpreadsheetCogMenu');
        }  
        return res
    }
})