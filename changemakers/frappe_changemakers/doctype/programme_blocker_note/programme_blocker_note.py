import frappe
from frappe.model.document import Document
from frappe.utils import get_first_day, getdate, now_datetime


class ProgrammeBlockerNote(Document):
    def before_save(self):
        if self.month:
            self.month = get_first_day(getdate(self.month))
        if self.resolved and not self.resolved_at:
            self.resolved_at = now_datetime()
        if not self.resolved:
            self.resolved_at = None
