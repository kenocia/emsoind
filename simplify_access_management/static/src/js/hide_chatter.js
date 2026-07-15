import { FormRenderer } from "@web/views/form/form_renderer";
import { session } from "@web/session";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
const { onMounted } = owl;

patch(FormRenderer.prototype, {
  setup() {
    super.setup();
    this.orm = useService("orm");
    const self = this;
    onMounted(async () => {
      let model = self.props.record.resModel;
      let cid = session.user_companies.current_company;
      let userId = session.storeData["res.partner"]?.[1]?.userId;

      if (cid && model) {
        await self.orm
          .call("access.management", "get_chatter_hide_details", [
            userId,
            cid,
            model,
          ])
          .then(function (result) { 
            let semd_msg_elem = document.querySelector(
              ".o-mail-Chatter-sendMessage"
            );
            let log_note_elem = document.querySelector(
              ".o-mail-Chatter-logNote"
            );
            let sche_activity_elem = document.querySelector(
              ".o-mail-Chatter-activity"
            );
            if (!result["hide_send_mail"]) {
              var btn1 = setInterval(function () {
                if (semd_msg_elem) {
                  semd_msg_elem.remove();
                  clearInterval(btn1);
                }
              }, 50);
            }
            if (!result["hide_log_notes"]) {
              var btn2 = setInterval(function () {
                if (log_note_elem) {
                  log_note_elem.remove();
                  clearInterval(btn2);
                }
              }, 50);
            }
            if (!result["hide_schedule_activity"]) {
              var btn3 = setInterval(function () {
                if (sche_activity_elem) {
                  sche_activity_elem.remove();
                  clearInterval(btn3);
                }
              }, 50);
            }
          });
      }
    });
  },
});
