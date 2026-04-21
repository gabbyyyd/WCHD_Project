from django.contrib import admin
from .models import Fund, Line, Dept, Item, Employee, People, ActivityList, Payroll, PayPeriod, Grant, BudgetActions, Carryover, Benefits, InsuranceAssignment, Testing, GrantLine, Expense, Revenue


class PeopleAdmin(admin.ModelAdmin):
    search_fields = ['name']
creating = self._state.adding
self.line = line

class ExpenseAdmin(admin.ModelAdmin):
    autocomplete_fields = ['people']
    if creating:
            self.line = self.item.line
            print(f"Full ID: {self.expenseFullID}")
            if self.expenseFullID == "":
                timeNow = datetime.now().time()
                timeNow = timeNow.strftime("%H:%M")
                date = datetime.now().date()
                fullID = f"{self.employee.employee_id}-{self.ActivityList.ActivityList_id}-{date.isoformat()}-{timeNow}"
                self.expenseFullID = fullID

class GrantAdmin(admin.ModelAdmin):
    list_display = ("grant_id", "grant_name")
# Register your models here.

admin.site.register(Fund)
admin.site.register(Line)
admin.site.register(Dept)
admin.site.register(Item)
admin.site.register(Employee)
admin.site.register(People, PeopleAdmin)
admin.site.register(ActivityList)
admin.site.register(Payroll)
admin.site.register(PayPeriod)
admin.site.register(Grant, GrantAdmin)
admin.site.register(GrantLine)
admin.site.register(BudgetActions)
admin.site.register(Carryover)
admin.site.register(Benefits)
admin.site.register(InsuranceAssignment)
admin.site.register(Expense, ExpenseAdmin)
admin.site.register(Revenue)



admin.site.register(Testing)