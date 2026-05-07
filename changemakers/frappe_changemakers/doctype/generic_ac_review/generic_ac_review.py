import frappe
from frappe.model.document import Document

class GenericACReview(Document):
    def before_save(self):
        if self.status in ("Cleared – Will Apply", "Blocked – No Resolution"):
            if not self.resolved_date:
                self.resolved_date = frappe.utils.today()
