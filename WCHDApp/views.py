from multiprocessing import context
from urllib import request

from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from .models import Fund, Testing, Item, Grant, GrantLine, Revenue, Expense, Line, People, ActivityList, InsuranceAssignment, InsurancePercentage, InsuranceAllocation, Employee
from django.db.models.fields.related import ForeignKey, ManyToManyField, OneToOneField
from .forms import TableSelect, InputSelect, ExportSelect,reconcileForm, FileInput, ProjectionCalcForm
from django.forms import modelform_factory, Select
from django import forms
from django.apps import apps
from django.db.models import DecimalField, AutoField
from django.db import models, transaction
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import permission_required, login_required
from django.contrib import messages
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from io import BytesIO
import re
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import PatternFill
import numpy as np
from datetime import datetime
import json
from django.shortcuts import render
from django.urls import reverse
from django.utils.timezone import now
from django.utils.dateparse import parse_datetime
from django.core.exceptions import ValidationError
import re
from decimal import Decimal
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import io
import base64
from decimal import ROUND_HALF_UP
from collections import defaultdict
import calendar
from datetime import date
from django.core.exceptions import PermissionDenied
from django.core.exceptions import ObjectDoesNotExist
import traceback
from django.contrib.admin.models import LogEntry
import csv
from django.contrib.admin.views.decorators import staff_member_required


def generate_pdf(request, tableName):
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(letter),
        rightMargin=20,
        leftMargin=20,
        topMargin=25,
        bottomMargin=25,
    )

    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Title"],
        fontSize=16,
        spaceAfter=11,
        fontName="Helvetica-Bold"
    )

    table_text_style = ParagraphStyle(
        "TableText",
        parent=styles["Normal"],
        fontSize=7,
        leading=9,
        wordWrap="CJK",
        alignment=0,
    )

    header_style = ParagraphStyle(
        "HeaderStyle",
        parent=styles["Normal"],
        fontSize=7,
        leading=8,
        alignment=1,
        fontName="Helvetica-Bold",
        wordWrap="CJK",
    )

    elements.append(Spacer(1, 12))
    elements.append(Paragraph("Washington County Health Department", title_style))
    elements.append(Spacer(1, 12))

    model = apps.get_model("WCHDApp", tableName)
    selected_ids = request.GET.getlist("selected_rows")

    queryset = model.objects.all()

    # Load related objects so foreign keys display as names instead of IDs
    if tableName.lower() == "revenue":
        queryset = queryset.select_related(
            "item",
            "people",
            "ActivityList",
            "employee",
            "line",
            "grantLine",
        )

    elif tableName.lower() == "expense":
        queryset = queryset.select_related(
            "item",
            "people",
            "ActivityList",
            "employee",
            "line",
            "grantLine",
        )

    if selected_ids:
        queryset = queryset.filter(id__in=selected_ids)

    fields = model._meta.get_fields()

    fieldNames = []
    aliasNames = []

    fieldsToSkip = [
        "line",
        "line_id",
        "grantLine",
        "grantLine_id",
    ]

    for field in fields:
        # Skip reverse relationships
        if field.is_relation and field.auto_created:
            continue

        # Skip line and grant line columns
        if field.name in fieldsToSkip:
            continue

        if field.is_relation:
            aliasNames.append(field.verbose_name)
            fieldNames.append(field.name)
        else:
            aliasNames.append(field.verbose_name)
            fieldNames.append(field.name)

    data = [[Paragraph(str(name).title(), header_style) for name in aliasNames]]

    for row in queryset:
        line = []

        for fieldName in fieldNames:
            value = getattr(row, fieldName, "")

            # If field has choices, show the readable display value
            fieldObject = model._meta.get_field(fieldName)

            if fieldObject.choices:
                displayMethod = f"get_{fieldName}_display"
                text = getattr(row, displayMethod)()

            # If foreign key, show the related object's string name
            elif fieldObject.is_relation:
                text = str(value) if value else ""

            else:
                text = str(value) if value is not None else ""

            line.append(Paragraph(text, table_text_style))

        data.append(line)

    col_count = max(len(r) for r in data)
    usable_width = landscape(letter)[0] - doc.leftMargin - doc.rightMargin

    # Default column widths
    col_widths = [usable_width / col_count] * col_count

    # Make common long-text columns wider
    for index, name in enumerate(aliasNames):
        lowerName = str(name).lower()

        if lowerName in ["id"]:
            col_widths[index] = 0.75 * inch

        elif "comment" in lowerName:
            col_widths[index] = 2.5 * inch

        elif "person" in lowerName or "people" in lowerName:
            col_widths[index] = 1.4 * inch

        elif "activity" in lowerName or "program" in lowerName:
            col_widths[index] = 1.4 * inch

        elif "employee" in lowerName:
            col_widths[index] = 1.3 * inch

        elif "amount" in lowerName:
            col_widths[index] = 0.75 * inch

        elif "date" in lowerName:
            col_widths[index] = 0.8 * inch

    # Rebalance if widths are too wide
    total_width = sum(col_widths)

    if total_width > usable_width:
        scale = usable_width / total_width
        col_widths = [width * scale for width in col_widths]

    table = Table(
        data,
        colWidths=col_widths,
        repeatRows=1,
        splitByRow=True,
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkgray),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),

        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("ALIGN", (0, 1), (-1, -1), "LEFT"),

        ("VALIGN", (0, 0), (-1, -1), "TOP"),

        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, 0), 6),

        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),

        ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
    ]))

    elements.append(table)

    elements.append(Spacer(1, 12))
    elements.append(Paragraph("340 Muskingum Drive, Suite B, Marietta, OH 45750", styles["Normal"]))
    elements.append(Paragraph("740.374.2782 www.washingtongov.org/health", styles["Normal"]))

    doc.build(elements)

    buffer.seek(0)
    pdf_data = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf_data, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{tableName}_report.pdf"'

    return response

def reconcile(request):
    if request.method == "POST":
        form = reconcileForm(request.POST, request.FILES)
        if form.is_valid():
            firstFile = form.cleaned_data['firstFile'] 
            secondFile = form.cleaned_data['secondFile'] 
            
            df1 = pd.read_csv(firstFile)
            df2 = pd.read_csv(secondFile)

            columnList = list(df1.columns)
            for i in range(len(columnList)):
                columnList[i] = columnList[i].strip()
            # Merge the two lists and remove duplicates
            merged_df = pd.concat([df1, df2]).drop_duplicates()

            # Identify common entries (entries in both list1 and list2)
            common_entries = df1.merge(df2, on=columnList, how="inner")

            # Save merged data to an Excel file
            output_file = "output.xlsx"
            merged_df.to_excel(output_file, index=False)

            # Load the saved Excel file for formatting
            wb = load_workbook(output_file)
            ws = wb.active

            # Define highlight style
            highlight_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")

            # Convert common entries into a set for fast lookup
            rows = common_entries[columnList].apply(tuple, axis=1)
            common_set = set(rows)
            print(common_set)

            # Apply highlighting to rows that are NOT common (i.e., unique to either list1 or list2)
            for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=1):
                rowData = []
                for column in row:
                    rowData.append(column.value)
                rowTuple = tuple(rowData)
                print(rowTuple)
                if rowTuple not in common_set:  # Highlight unique entries only
                    for cell in row:
                        cell.fill = highlight_fill
            
            #Saveing to stream in file attachment format
            outputStream = BytesIO()
            wb.save(outputStream)
            outputStream.seek(0)
            response = HttpResponse(outputStream.getvalue(),content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="reconciliation.xlsx"'

            return response
    else:
        form = reconcileForm()
    return render(request, "WCHDApp/reconcile.html", {"form":form})

#This view is used to select what table we want to create a report from
def reports(request):
    if request.method == "POST":
        #TableSelect is a form defined in forms.py
        form = TableSelect(request.POST)

        #Take the data from the form and pass it to our pdf generator function
        button = request.POST.get('button')
        if form.is_valid():
            tableName = form.cleaned_data['table'] 
            if button == "daily":
                return redirect('dailyReport')
            if tableName == "InsuranceReports":
                return redirect("insuranceReports")
            else:
                return redirect('generate_pdf', tableName)
    else:
        form = TableSelect()
    return render(request, "WCHDApp/reports.html", {'form': form})

def index(request):
    # Set session start time if it's not already set
    if not request.session.get('session_start_time'):
        request.session['session_start_time'] = str(now())

    # Calculate session duration
    session_start_str = request.session.get('session_start_time')
    duration_display = "0h 0m 0s"  # Default

    todayDate = datetime.today()

    #For displaying totals for the day
    expenses = Expense.objects.filter(date=todayDate)
    revenues = Revenue.objects.filter(date=todayDate)

    expenseTotal = 0
    revenueTotal = 0
    for expense in expenses:
        expenseTotal += expense.amount

    for revenue in revenues:
        revenueTotal += revenue.amount

    if session_start_str:
        session_start = parse_datetime(session_start_str)
        if session_start:
            duration = now() - session_start
            total_seconds = int(duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            duration_display = f"{hours}h {minutes}m {seconds}s"
    
    context ={
        'duration': duration_display,
        "revenueTotal": revenueTotal,
        "expenseTotal": expenseTotal
    }

    # Pass formatted string to template
    return render(request, "WCHDApp/index.html", context)

#Login page logic
def logIn(request):
    #Getting username and password from the form
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        #If authentication is successful, returns related user object
        #notAdmin pass is Marietta123
        #Django implemented function to check databse for user and rights etc
        user = authenticate(request, username = username, password=password)

        #If authenticated, login (Django function) and redirect to hub
        #If not give error 
        if user is not None:
            login(request,user)
            return redirect('index')
        else:
            messages.error(request, "Invalid username or password")
    return render(request, "WCHDApp/logIn.html")

#Logic to get what tables we want to see/create from. Same thing as reports
def viewTableSelect(request):
    if request.method == 'POST':
        form = TableSelect(request.POST)

        #Logic to figure out which button sent the request so that we can correctly redirect
        #Each button has a different value aligning to their names, this is set in the html file "viewTableSelect"
        button = request.POST.get('button')
        #Redirect for custom views else use default dynamic view
        #All of these redirect are to different views in this file named accordingly
        if form.is_valid():
            tableName = form.cleaned_data['table'] 
            if tableName == 'Payroll':
                return redirect('payrollView')
            elif tableName == "Transaction":
                return redirect('transactionCustomView')
            elif tableName == "GrantExpense":
                return redirect('grantExpenses')
            elif tableName == "Expense":
                return redirect('transactionsExpenses')
            elif tableName == "Revenue":
                return redirect('transactionsItem')
            elif tableName == "Line":
                return redirect('lineView')
            elif tableName == "Item":
                return redirect('itemView')
            elif tableName == "GrantLine":
                return redirect('grantLineView')
            if button == "seeTable":
                return redirect('tableView', tableName)
            elif button == "create":
                return redirect('createEntry', tableName)
    else:
        form = TableSelect()
    return render(request, "WCHDApp/viewTableSelect.html", {'form': form})

#This function decides what data we use in our tables in tableView.html
@login_required
def tableView(request, tableName):

    permission_name = f'WCHDApp.view_{tableName.lower()}'

    if not request.user.has_perm(permission_name):
        raise PermissionDenied

    #Grabbing the model selected in viewTableSelect
    model = apps.get_model('WCHDApp', tableName)

    #Getting data from that model
    values = model.objects.all()

    #Getting just field names from model
    #Use .fields instead of .get_fields() because we do not want reverse relationships
    fields = model._meta.fields

    #Any property that we define in models need to go here so our logic can include them in the table
    calculatedProperties = {
        "Testing": [("fundBalanceMinus3", "Fund Balance Minus 3")],
        "Payroll": [("pay_rate", "Pay Rate")],
        "Fund":[("calcRemaining", "Remaining Expense"), ("actualRevenue", "Actual Revenue"), ("budgetedRevenue", "Budgeted Revenue"),("budgetedExpense", "Budgeted Expense"),],
        "GrantLine": [("budgetRemaining", "Budget Remaining"), ("budgetSpent", "Budget Spent"), ("totalIncome", "Total Income")],
        "Grant": [("grantAwardAmountRemaining", "Grant Award Amount Remaining"),( "recieved","Recieved")]
    }

    #This is used to decide which fields we want to show in the accumulator based on each model
    summedFields = {
        "Fund": "fund_cash_balance", 
        "Line": "line_total_income",
        "Transaction": "amount",
        "BudgetActions": "amount",
    }
    

    fieldNames = []
    aliasNames = []
    decimalFields = []
    for field in fields:
        if isinstance(field, DecimalField):
                decimalFields.append(field.name)
        aliasNames.append(field.verbose_name)  
        fieldNames.append(field.name)
    #Making sure properties are added like normal fields to the tables
    if tableName in calculatedProperties:
        for property in calculatedProperties[tableName]:
            #print(property)
            aliasNames.append(property[1])
            fieldNames.append(property[0])
            decimalFields.append(property[0])

    def fixedTableName(tableName):
        return re.sub(r'(?<!^)(?=[A-Z])', ' ', tableName)

    tableName = fixedTableName(tableName)

    context = {
        "fields" : fieldNames,
        "aliasNames": aliasNames,
        "data": values,
        "tableName" : tableName,
        "decimalFields" : decimalFields,
    }
    
    if tableName == "Fund":
        total_remaining = Decimal("0.00")
        total_budgeted = Decimal("0.00")

        for f in values:
            total_remaining += (f.calcRemaining or Decimal("0.00"))
            total_budgeted += (f.budgeted or Decimal("0.00"))

        context["total_remaining"] = total_remaining
        context["total_budgeted"] = total_budgeted
    #Getting values based on if we defined them in summedFields in order to make accumulator
    if tableName in summedFields:
        field = summedFields[tableName]

        accumulator = values.aggregate(
            total=Coalesce(Sum(field), Value(Decimal("0.00")))
        )["total"]
        context["accumulator"] = accumulator
        

    return render(request, "WCHDApp/tableView.html", context)

#New system to dynamically create forms based of model
#Default way of creating objects dynamically based on table name
#Some have overrides as stated above
@login_required
def createEntry(request, tableName):

    permission_name = f'WCHDApp.add_{tableName.lower()}'

    if not request.user.has_perm(permission_name):
        raise PermissionDenied
    message = ""
    #Grabbing selected model in viewTableSelect
    model = apps.get_model('WCHDApp', tableName)

    if request.method == 'POST':
        #Django function that makes a form based off a provided model
        #FORM UPDATES IF NEEDED, MAKE SURE TO ADD EXCLUSIONS IN NON_POST RENDER AS WELL

        if tableName == "Fund":
            form = modelform_factory(model, exclude=["fund_total"])(request.POST)
        else:
            form = modelform_factory(model, fields="__all__")(request.POST)

      
        if form.is_valid():
            form.save()
            return redirect('tableView', tableName)
        else:
            print(form.errors)
    else:
        if tableName == "Fund":
            form = modelform_factory(model, exclude=["fund_total"])()
        else:
            form = modelform_factory(model, fields="__all__")()
    return render(request, "WCHDApp/createEntry.html", {"form": form, "tableName": tableName, "message": message})


def renameOldImportColumns(tableName, file):
    columnMap = {}

    if tableName == "ActivityList":
        columnMap = {
            "ActivityList_id": "ActivityList_id",
            "dept_id": "dept_id",
            "fund_id": "fund_id",
            "item_id": "item_id",
        }

    elif tableName == "Item":
        columnMap = {
            "item_id": "item_id",
            "fund_id": "fund_id",
            "line_id": "line_id",
        }

    elif tableName == "Line":
        columnMap = {
            "line_id": "line_id",
            "fund_id": "fund_id",
            "dept_id": "dept_id",
        }

    elif tableName == "Fund":
        columnMap = {
            "fund_id": "fund_id",
            "dept_id": "dept_id",
        }

    elif tableName == "Revenue":
        columnMap = {
            "item_id": "item_id",
            "people_id": "people_id",
            "ActivityList_id": "ActivityList_id",
            "line_id": "line_id",
            "employee_id": "employee_id",
            "grantLine_id": "grantLine_id",
        }

    elif tableName == "Expense":
        columnMap = {
            "item_id": "item_id",
            "people_id": "people_id",
            "ActivityList_id": "ActivityList_id",
            "line_id": "line_id",
            "employee_id": "employee_id",
            "grantLine_id": "grantLine_id",
        }

    return file.rename(columns=columnMap)

#Default import logic, payroll has its own logic and is redirect to its own view
def cleanImportValue(value):
    """
    Cleans values coming from old CSV files.
    """

    if value is None:
        return None

    value = str(value).strip()

    if value == "" or value.lower() == "nan":
        return None

    # Converts values like 56.0 into 56
    if value.endswith(".0"):
        value = value[:-2]

    return value

def convertOldImportValue(tableName, column, value):
    if value is None:
        return None

    value = str(value).strip()

    # Any column that points to a Fund may have old values like 2026-6000.
    # The new Fund primary key only wants 6000.
    fundColumns = [
        "fund_id",
        "adminPayFund_id",
        "specialFund_id",
    ]

    if column in fundColumns and "-" in value:
        return value.split("-")[-1]

    return value

def cleanDateValue(value):
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    dateFormats = [
        "%Y-%m-%d",   # 2025-12-29
        "%m/%d/%Y",   # 12/29/2025
        "%m/%d/%y",   # 12/29/25
    ]

    for dateFormat in dateFormats:
        try:
            return datetime.strptime(value, dateFormat).date()
        except ValueError:
            pass

    return value

def imports(request):
    message = ""

    if request.method == "POST":
        form = InputSelect(request.POST, request.FILES)

        if form.is_valid():
            tableName = form.cleaned_data["table"]

            if tableName == "Payroll":
                return redirect("clockifyImportPayroll")

            selectedFile = form.cleaned_data["file"]

            if tableName == "InsurancePercentage":
                success, message = processInsurancePercentageImport(selectedFile)
                return render(
                    request,
                    "WCHDApp/imports.html",
                    {
                        "form": form,
                        "message": message,
                    }
                )

            try:
                # Read every value as text so IDs do not become weird decimals
                file = pd.read_csv(selectedFile, dtype=str).fillna("")
                file.columns = [column.strip() for column in file.columns]

                model = apps.get_model("WCHDApp", tableName)
                modelFields = model._meta.get_fields()

                neededFields = []

                for field in modelFields:
                    # Skip reverse relationships and Django-created fields
                    if field.auto_created:
                        continue

                    # ForeignKey fields need the actual database column name,
                    # like fund_id instead of fund
                    if field.is_relation:
                        neededFields.append(field.attname)
                    else:
                        neededFields.append(field.name)

                csvColumns = list(file.columns)

                missingFields = []

                for fieldName in neededFields:
                    if fieldName not in csvColumns:
                        missingFields.append(fieldName)

                if missingFields:
                    message = f"Bad File. Missing columns: {missingFields}"
                    return render(
                        request,
                        "WCHDApp/imports.html",
                        {
                            "form": form,
                            "message": message,
                        }
                    )

                importedCount = 0
                skippedCount = 0

                for i in range(len(file)):
                    row = file.iloc[i]
                    line = {}

                    for column in csvColumns:
                        if column in neededFields:
                            if tableName == "Employee" and column == "user_id":
                                continue
                            cleanedValue = cleanImportValue(row[column])
                            cleanedValue = convertOldImportValue(tableName, column, cleanedValue)

                            if column in ["date", "dob", "hire_date"]:
                                cleanedValue = cleanDateValue(cleanedValue)

                            line[column] = cleanedValue

                    pkField = model._meta.pk
                    pkName = pkField.name
                    hasAutoPrimaryKey = pkField.auto_created

                    if not hasAutoPrimaryKey:
                        if pkName not in line:
                            message = f"Bad File. Missing primary key column: {pkName}"
                            return render(request, "WCHDApp/imports.html", {"form": form, "message": message})

                        if line[pkName] is None:
                            skippedCount += 1
                            continue

                    # Do not pass None into non-nullable fields if the CSV is blank
                    cleanLine = {}

                    for key, value in line.items():

                        # Special fix for blank grantLine_id values
                        if key == "grantLine_id" and (value is None or value == ""):
                            cleanLine[key] = None
                            continue

                        try:
                            field = model._meta.get_field(key)
                        except:
                            if key.endswith("_id"):
                                field = model._meta.get_field(key[:-3])
                            else:
                                raise

                        if value is None:
                            if field.null or field.blank:
                                cleanLine[key] = None
                            else:
                                continue
                        else:
                            cleanLine[key] = value

                    if hasAutoPrimaryKey:
                        if pkName in cleanLine:
                            cleanLine.pop(pkName)

                        obj = model(**cleanLine)

                        # Imported old Revenue/Expense records should not change fund balances again
                        if tableName in ["Revenue", "Expense"]:
                            obj._importing_old_data = True

                        obj.save()
                        importedCount += 1

                message = f"{tableName} imported successfully. Imported: {importedCount}. Skipped: {skippedCount}."

            except ObjectDoesNotExist as e:
                message = f"Import failed. A related record does not exist: {e}"

            except Exception as e:
                print(traceback.format_exc())
                message = f"Import failed: {e}"

        else:
            message = "Bad form. Please select a table and upload a CSV file."

    else:
        form = InputSelect()

    return render(
        request,
        "WCHDApp/imports.html",
        {
            "form": form,
            "message": message,
        }
    )

@login_required
@permission_required('WCHDApp.manage_exports', raise_exception=True)
def exports(request):
    message = ""

    if request.method == 'POST':
        form = ExportSelect(request.POST)

        if form.is_valid():
            tableName = form.cleaned_data['table']
            fileName = form.cleaned_data['fileName']

            model = apps.get_model('WCHDApp', tableName)
            queryset = model.objects.all()

            start_date = form.cleaned_data['start_date']
            end_date = form.cleaned_data['end_date']

            # If date filtering entered for Revenue or Expense, filter based on date range
            if tableName in ["Revenue", "Expense"]:
                if start_date:
                    queryset = queryset.filter(date__gte=start_date)

                if end_date:
                    queryset = queryset.filter(date__lte=end_date)

            exportRows = []

            fields = model._meta.fields

            for obj in queryset:
                row = {}

                for field in fields:
                    fieldName = field.name
                    verboseName = field.verbose_name

                    value = getattr(obj, fieldName)

                    # If this field has choices, export the display value
                    if field.choices:
                        displayMethod = f"get_{fieldName}_display"
                        value = getattr(obj, displayMethod)()

                    # If this is a foreign key, export the object's string value instead of the ID
                    elif field.is_relation:
                        if value is not None:
                            value = str(value)
                        else:
                            value = ""

                    # Otherwise, export the normal value
                    else:
                        if value is None:
                            value = ""

                    row[verboseName] = value

                exportRows.append(row)

            exportData = pd.DataFrame(exportRows)

            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{fileName}.csv"'

            exportData.to_csv(path_or_buf=response, index=False)
            return response

    else:
        form = ExportSelect()

    return render(request, "WCHDApp/exports.html", {"form": form, "message": message})

def countyPayrollExport(request):
    payperiodModel = apps.get_model('WCHDApp', "PayPeriod")
    payperiods = payperiodModel.objects.all()

    if request.method == "POST":
        payperiod = request.POST.get('payPeriod')
        fileName = request.POST.get('fileName')

        payrollModel = apps.get_model('WCHDApp', "Payroll")
        entries = payrollModel.objects.select_related('employee', "ActivityList").filter(payperiod__payperiod_id = payperiod)

        #Values for mapping codes later in code
        employeeHoursByActivity = {}
        codeMappings = {
            "SICK": "S",
            "COMP": "C",
            "VAC": "V",
            "HOLIDAY": "H"
        }

        secondaryMapping = {
            "S": "S-SICK",
            "C":  "C-COMPTIME",
            "V": "V-VACATION",
            "H": "H-HOLIDAY",
            "R": "R-REGULAR PA"
        }

        for entry in entries:
            activityName = entry.ActivityList.program.upper()
            #If the Activity contains a word that is present in codeMapping aka "SICK" it sets the paycode to the abbreviation
            for keyword, code in codeMappings.items():
                if keyword in activityName:
                    paycode = code
                    break
                else:
                    paycode = "R"
            #Reverting back to a full name
            paycodeName = secondaryMapping[paycode]

            #Creating a dictionary that holds employees hours with paycodes as keys to make running totals
            if paycodeName not in employeeHoursByActivity:
                employeeHoursByActivity[paycodeName] = {}

            if entry.employee in employeeHoursByActivity[paycodeName]:
                employeeHoursByActivity[paycodeName][entry.employee] += entry.hours
            else:
                employeeHoursByActivity[paycodeName][entry.employee] = entry.hours

        #Creating the csv export
        exportData = []
        for activity, employeeDict in employeeHoursByActivity.items():
            for employee, hours in employeeDict.items():
                line = employee.payItem.line
                fullID = line.line_id
                splitID = fullID.split("-")
                if len(splitID)==3:
                    year, fundID, lineID = splitID[0], splitID[1], splitID[2]
                else:
                    fundID, lineID = splitID[0], splitID[1]
                
                accountDistribution = f"{fundID}50290{lineID}"
                exportData.append({
                    "JobNumber": employee.employee_id,
                    "Paycode": activity,
                    "Time Group/Description": "",
                    "Hours": hours,
                    "HourlyRate": employee.pay_rate,
                    "Salary": "",
                    "AccountDistribution": accountDistribution
                })
        exportData = pd.DataFrame(exportData)
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="{fileName}.csv"'
        exportData.to_csv(path_or_buf=response, index=False)

        return response

    context = {
        "payperiods": payperiods
    }
    return render(request, "WCHDApp/countyPayrollExport.html", context)

#This is for revenue but was named previous to table split
def transactionsItem(request):
    #This view is just to pull what item we want and pass it to the partial
    #This is a common pattern you will see 
    #TransactionsView is the partial linked to this view others are named better
    itemModel = apps.get_model('WCHDApp', "Item")
    itemValues = itemModel.objects.filter(line__lineType="Revenue")
    if request.method == "POST":
        itemID = request.POST.get('itemSelect')
        return redirect(transactionsView,itemID)
    
    return render(request, "WCHDApp/transactionsItem.html", {"items":itemValues})

def transactionsView(request):
    message = ""
    revenueModel = apps.get_model('WCHDApp', "revenue")
    itemID = request.GET.get('itemSelect')
    sort_by = request.GET.get('sort_by')
    revenueValues = revenueModel.objects.filter(item_id=itemID)

    #Filter for sorting by date range
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    if start_date and end_date:
        revenueValues = revenueValues.filter(date__range=[start_date, end_date])
    elif start_date:
        revenueValues = revenueValues.filter(date__gte=start_date)
    elif end_date:
        revenueValues = revenueValues.filter(date__lte=end_date)

    revenueValues = revenueValues.order_by("date")

    if sort_by:
        revenueValues = revenueValues.order_by(sort_by)

    accumulator = 0
    for r in revenueValues:
        accumulator += r.amount

    #Getting just field names from model
    fields = revenueModel._meta.get_fields()

    #Lists to sort fields for styling
    fieldNames = []
    decimalFields = []
    aliasNames = []
   
    #Fields that should be accumulated
    summedFields = {
        "Fund": "fund_cash_balance", 
        "Line": "line_total_income",
        "Transaction": "amount",
    }

    for field in fields:
        if isinstance(field, DecimalField):
                decimalFields.append(field.name)
        aliasNames.append(field.verbose_name)  
        fieldNames.append(field.name)

            
    #Making the view for the cashiers to be able to see and add transaction on the same page
    RevenueForm = modelform_factory(revenueModel, exclude=(["item", "date", "line", "employee"]),  
                                    widgets={
                                        'people': forms.Select(attrs={'class': 'searchable-select'}),
                                        'grantLine': forms.Select(attrs={'class': 'searchable-select'}),
                                    })

    #Getting values from our db so they dont have to
    item = Item.objects.get(pk=itemID)

    if request.method == 'POST':
        form = RevenueForm(request.POST)

        employeeModel = apps.get_model('WCHDApp', "employee")
        employee = employeeModel.objects.filter(user=request.user).first()

        if not employee:
            message = "No employee with signed in user"

        else:
            if form.is_valid():
                revenue = form.save(commit=False)

                revenue.employee = employee
                revenue.item = item

                revenue.save()

                message = "Revenue Posted Successfully"
                form = RevenueForm()

            else:
                errors = form.errors

                if errors.get("grantLine"):
                    message = errors["grantLine"][0]
                else:
                    message = "Revenue could not be posted. Please check the form."

    else:
        form = RevenueForm()

    context = {
        "itemObj": item,
        "item": itemID,
        "revenue": revenueValues,  # optional, for other purposes
        "data": revenueValues,     # <--- THIS MUST BE THE FILTERED QUERYSET
        "fields": fieldNames,
        "aliasNames": aliasNames,
        "decimalFields": decimalFields,
        "form": form,
        "message": message,
        "accumulator": accumulator,
    }

    #return render(request, "WCHDApp/transactionsView.html", {"item": itemID, "revenue": revenueValues,"fields": fieldNames, "aliasNames": aliasNames, "data": revenueValues, "decimalFields": decimalFields, "form":form})
    #return render(request, "WCHDApp/partials/revenueTableAndForm.html", {"itemObj":item, "item": itemID, "revenue": revenueValues,"fields": fieldNames, "aliasNames": aliasNames, "data": revenueValues, "decimalFields": decimalFields, "form":form, "message":message})
    # Detect HTMX requests
    """if request.headers.get("HX-Request"):
        # Return only the partial for HTMX swaps
        return render(request, "WCHDApp/partials/revenueTableAndForm.html", context)
    else:
        # Return full page for normal GET
        return render(request, "WCHDApp/transactionsView.html", context)"""
    if request.headers.get("HX-Request"):
        return render(request, "WCHDApp/partials/revenueTableAndForm.html", context)

    return render(request, "WCHDApp/transactionsView.html", context)

#Used to create a people form within another form for entry time creation
def addPeopleForm(request):
    peopleModel = apps.get_model("WCHDApp", "people")
    PeopleForm = modelform_factory(peopleModel, fields="__all__")
    itemID = request.GET.get("itemID")
    source = request.GET.get("source")

    if request.method == "POST":
        form = PeopleForm(request.POST)
        itemID = request.POST.get("itemID")
        source = request.POST.get("source")
        if form.is_valid():
            form.save()
            if source == "revenue":
                return redirect('transactionsItem')
            else:
                return redirect('transactionsExpenses')
    else:
        form = PeopleForm()
    context ={
        "form": form,
        "itemID": itemID,
        "source": source
    }

    return render(request, "WCHDApp/partials/formPartial.html", context)

#these are named transaction expense because it was originally built on the transactions table whihc then got split into 2 different tables
def transactionsExpenses(request):
    itemModel = apps.get_model("WCHDApp", "Item")
    items = itemModel.objects.filter(line__lineType="Expense")


    if request.method=="POST":
        print("Submitted")
    context = {
        "items": items
    }
    return render(request, "WCHDApp/transactionsExpenses.html", context)

def transactionsExpenseTableUpdate(request):
    message = ""
    itemID = request.GET.get('item')
    #print(itemID)
    expenseModel = apps.get_model('WCHDApp', "expense")
    expenseValues = expenseModel.objects.filter(item_id=itemID)

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    sort_by = request.GET.get("sort_by")

    if start_date and end_date:
        expenseValues = expenseValues.filter(date__range=[start_date, end_date])
    elif start_date:
        expenseValues = expenseValues.filter(date__gte=start_date)
    elif end_date:
        expenseValues = expenseValues.filter(date__lte=end_date)

    allowedSorts = [
        "date", "-date",
        "amount", "-amount",
        "item", "-item",
        "people", "-people",
        "employee", "-employee",
    ]

    if sort_by in allowedSorts:
        expenseValues = expenseValues.order_by(sort_by)
    else:
        expenseValues = expenseValues.order_by("date")

    accumulator = 0
    for e in expenseValues:
        accumulator += e.amount

    #Getting just field names from model
    fields = expenseModel._meta.get_fields()

    #Lists to sort fields for styling
    fieldNames = []
    decimalFields = []
    aliasNames = []

    #Fields that should be accumulated
    summedFields = {
        "Fund": "fund_cash_balance", 
        "Line": "line_total_income",
        "Transaction": "amount",
    }

    for field in fields:
        if isinstance(field, DecimalField):
                decimalFields.append(field.name)
        aliasNames.append(field.verbose_name)  
        fieldNames.append(field.name)

    #Making the view for the cashiers to be able to see and add transaction on the same page
    expenseForm = modelform_factory(expenseModel, exclude=(["item", "date", "line", "employee", "expenseFullID"]),  
                                    widgets={
                                        'people': forms.Select(attrs={'class': 'searchable-select'}),
                                        'grantLine': forms.Select(attrs={'class': 'searchable-select'}),
                                    })

    #Getting values from our db so they dont have to
    item = Item.objects.get(pk=itemID)  
    #print(item)

    if request.method == 'POST':
        #print("SUBMITTED ON TABLE UPDATE")
        form = expenseForm(request.POST)
        form.instance.item = item
        user  = request.user
        try:
            employeeModel = apps.get_model('WCHDApp', "employee")
            employee = employeeModel.objects.filter(user=request.user).first()
            form.instance.employee = employee
        except:
            message = "No employee with signed in user"
        
        #print(request.POST)
        if form.is_valid():
            #Create the instance but don't save it yet
            expense = form.save()
            message = "Expense Posted Successfully"
            form = expenseForm()
        else:
            errors = form.errors
            if errors.get("amount"):
                message = errors["amount"][0]     
            
    else:
        form = expenseForm()

    line = item.line
    context = {
        "expenses": expenseValues,
        "fields": fieldNames, 
        "aliasNames": aliasNames, 
        "data": expenseValues, 
        "decimalFields": decimalFields,
        "form": form,
        "item": item,
        "message": message,
        "budgeted_remaining": line.budgetRemaining,
        "accumulator" : accumulator,
    }

    return render(request, "WCHDApp/partials/transactionsTablePartial.html", context)

def lineView(request):
    funds = Fund.objects.all()
    
    context = {
        "funds": funds
    }
    return render(request, "WCHDApp/lineView.html", context)

@login_required
@permission_required('WCHDApp.change_line', raise_exception=True)
def lineTableUpdate(request):
    message = ""
    fundID = request.GET.get("fund")
    fund = Fund.objects.get(pk=fundID)
    
    Line = apps.get_model('WCHDApp', "line")
    lines = Line.objects.filter(fund=fund)

    #Getting just field names from model
    fields = Line._meta.fields

    #Lists to sort fields for styling
    fieldNames = []
    decimalFields = []
    aliasNames = []

    calculatedProperties = {
        "Testing": [("fundBalanceMinus3", "Fund Balance Minus 3")],
        "Payroll": [("pay_rate", "Pay Rate")],
        "Fund":[("calcRemaining", "Remaining"), ("budgeted", "Budgeted")],
        "Line": [("budgetRemaining", "Budget Remaining"), ("budgetSpent", "Budget Spent"), ("totalIncome", "Total Income")]
    }

    #Fields that should be accumulated
    summedFields = {
        "Fund": "fund_cash_balance", 
        "Line": "line_total_income",
        "Transaction": "amount",
    }

    for field in fields:
        if isinstance(field, DecimalField):
                decimalFields.append(field.name)
        aliasNames.append(field.verbose_name)  
        fieldNames.append(field.name)
    #Making sure properties are added like normal fields to the tables
    if "Line" in calculatedProperties:
        for property in calculatedProperties["Line"]:
            #print(property)
            aliasNames.append(property[1])
            fieldNames.append(property[0])
            decimalFields.append(property[0])
    if request.method == 'POST':
        #Excluding fields that are automatic in the model side
        form = modelform_factory(Line, exclude=["fund", "fund_year"])(request.POST)
        form.instance.fund = fund
        form.instance.fund_year = fund.year
        if form.is_valid():
            line = form.save()
            message = "Line created successfully"
            form = modelform_factory(Line, exclude=["fund", "fund_year"])()
        else:
            errors = form.errors
            if errors.get("line_budgeted"):
                message = errors["line_budgeted"][0]     
 
    else:
        form = modelform_factory(Line, exclude=["fund", "fund_year"])()
    

    #remainingToBudget = fund.fund_cash_balance - fund.fund_budgeted
    context = {
        "fields": fieldNames, 
        "aliasNames": aliasNames, 
        "data": lines, 
        "decimalFields": decimalFields,
        "form": form,
        "fund": fund,
        "message": message,
        "remainingToBudget": fund.totalAvailable
    }

    return render(request, "WCHDApp/partials/lineTableUpdate.html", context)

def itemView(request):
    lines = Line.objects.all()
    context = {
        "lines": lines,
    }
    return render(request, "WCHDApp/itemView.html", context)

@login_required
@permission_required('WCHDApp.change_item', raise_exception=True)
def itemTableUpdate(request):
    message = ""
    lineID = request.GET.get("line")
    line = Line.objects.get(pk=lineID)
    
    items = Item.objects.filter(line=line)

    #Getting just field names from model
    fields = Item._meta.fields

    #Lists to sort fields for styling
    fieldNames = []
    decimalFields = []
    aliasNames = []

    calculatedProperties = {
        "Testing": [("fundBalanceMinus3", "Fund Balance Minus 3")],
        "Payroll": [("pay_rate", "Pay Rate")],
        "Fund":[("calcRemaining", "Remaining"), ("budgeted", "Budgeted")],
        "Line": [("budgetRemaining", "Budget Remaining"), ("budgetSpent", "Budget Spent"), ("totalIncome", "Total Income")],
        "GrantLine": [("budgetRemaining", "Budget Remaining"), ("budgetSpent", "Budget Spent"), ("totalIncome", "Total Income")]
    }

    #Fields that should be accumulated
    summedFields = {
        "Fund": "fund_cash_balance", 
        "Line": "line_total_income",
        "Transaction": "amount",
    }

    for field in fields:
        if isinstance(field, DecimalField):
                decimalFields.append(field.name)
        aliasNames.append(field.verbose_name)  
        fieldNames.append(field.name)

    if "Item" in calculatedProperties:
        for property in calculatedProperties["Item"]:
            #print(property)
            aliasNames.append(property[1])
            fieldNames.append(property[0])
            decimalFields.append(property[0])

    if request.method == 'POST':
        form = modelform_factory(Item, exclude=["line", "fund", "fund_year", "fund_type"])(request.POST)
        form.instance.line = line
        form.instance.fund = line.fund
        form.instance.fund_year = line.fund_year
    
        if form.is_valid():
            item = form.save()
            message = "Item Created Successfully"
            form = modelform_factory(Item, exclude=["line", "fund", "fund_year", "fund_type"])()
        else:
            errors = form.errors
            if errors.get("line_budgeted"):
                message = errors["line_budgeted"][0]     
            if errors.get("lineType"):
                message = errors["lineType"][0]           
    else:
        form = modelform_factory(Item, exclude=["line", "fund", "fund_year", "fund_type"])()

    context = {
        "fields": fieldNames, 
        "aliasNames": aliasNames, 
        "data": items, 
        "line": line,
        "decimalFields": decimalFields,
        "form": form,
        "message": message,
    }

    return render(request, "WCHDApp/partials/itemTableUpdate.html", context)

def dailyReport(request):
    buffer = BytesIO()

    # Create a PDF
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()


    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Title"],
        fontSize=16,
        spaceAfter=11,
        fontName="Helvetica-Bold"
    )

    subtitle_style = ParagraphStyle(
        "SubtitleStyle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.black,
        spaceAfter=6,
        fontName="Helvetica-Oblique"
    )


    #logo = Image("logo.png", width=80, height=80)
    #logo.hAlign = 'LEFT'
    #elements.append(logo)

    elements.append(Spacer(1, 12))

    # Report Title
    elements.append(Paragraph("Washington County Health Department", title_style))
    elements.append(Paragraph(
        "List of Active Grants. Active means they have been awarded and the final expenditure report has not yet been approved.",
        subtitle_style
    ))

    elements.append(Spacer(1, 12))

    #Same logic as tableView, needs updated to current 
    model = apps.get_model('WCHDApp', 'transaction')
    today = datetime.today().strftime('%Y-%m-%d')
    values = model.objects.filter(date=today).values()
    fields = model._meta.get_fields()
    fieldNames = []
    decimalFields = []
    aliasNames = []
    for field in fields:
        if field.is_relation:
            if field.auto_created:
                continue
            else:
                parentModel = apps.get_model('WCHDApp', field.name)
                fkName = parentModel._meta.pk.name
                fkAlias = parentModel._meta.pk.verbose_name
                aliasNames.append(fkAlias)
                fieldNames.append(fkName)

        else:
            if isinstance(field, DecimalField):
                decimalFields.append(field.name)
            aliasNames.append(field.verbose_name)  
            fieldNames.append(field.name)

    data = [
        aliasNames,
    ]
    
    for row in values:
        print(row)
        line = []
        for field in fieldNames:
            line.append(row[field])
        data.append(line)


    # Table Styling
    table = Table(data, colWidths=[80, 70, 70, 70, 70, 50, 100, 50, 90, 40])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkgray),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 10),
    ]))

    elements.append(table)

    # Totals (below table)
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("<b>Total Active Grants:</b> $571,880.00", styles["Normal"]))
    elements.append(Paragraph("<b>Total Amount for Project:</b> $19,144.00", styles["Normal"]))

    #Build PDF
    doc.build(elements)

    # Get the PDF value from buffer
    buffer.seek(0)
    pdf_data = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf_data, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="testing.pdf"'

    return response

def testing(request):
    model = apps.get_model("WCHDApp", "Employee")
    objects = model.objects.all()
    fields = model._meta.fields
    fieldNames = []
    verboseNames = []
    for field in fields:
        verboseNames.append(field.verbose_name)
        fieldNames.append(field.name)
    
    context = {
        "objects": objects,
        "verboseNames": verboseNames,
        "fieldNames": fieldNames
    }

    return render(request, "WCHDApp/testing.html", context)

def checkPrivileges(request):
    print("Checking privileges")
    if (request.user.is_staff):
        print("Staff")
        return redirect(noPrivileges)  
    else:
        return None 
    
def noPrivileges(request, exception):
    return render(request, "WCHDApp/noPrivileges.html")

@login_required
@permission_required('WCHDApp.process_payroll', raise_exception=True)
def clockifyImportPayroll(request, *args, **kwargs):
    message = ""

    fieldMap = {
        "Project": "ActivityList",
        "User": "employee",
        "Start Date": "beg_date",
        "End Date": "end_date",
        "Billable Amount (USD)": "pay_amount",
        "Duration (decimal)": "hours",
    }

    if request.method == 'POST':
        form = FileInput(request.POST, request.FILES)

        if form.is_valid():
            selectedFile = form.cleaned_data['file']
            dateInputted = request.POST.get("date")

            try:
                file = pd.read_csv(selectedFile)
                file.dropna(how='all', inplace=True)
            except Exception as e:
                message = f"Could not read file: {e}"
                return render(
                    request,
                    "WCHDApp/clockifyImportPayroll.html",
                    {"form": form, "message": message}
                )

            data = []

            payrollModel = apps.get_model('WCHDApp', 'Payroll')
            fields = payrollModel._meta.get_fields()

            fks = []
            for field in fields:
                if field.is_relation:
                    fks.append(field.name)

            # Keep original CSV column names separate
            source_columns = list(file.columns)

            # Build list 
            mapped_columns = []
            for source_col in source_columns:
                if source_col in fieldMap:
                    mapped_columns.append((source_col, fieldMap[source_col]))

            # Build dictionaries
            for _, row in file.iterrows():
                row_dict = {}

                try:
                    startTime = str(row["Start Time"])
                    startTimeHour = startTime.split(" ")[0]
                except Exception:
                    startTimeHour = ""

                for source_col, model_col in mapped_columns:
                    value = row[source_col]

                    if pd.isna(value):
                        value = None

                    if model_col in ["beg_date", "end_date"] and value is not None:
                        try:
                            newDate = datetime.strptime(str(value), "%m/%d/%Y").date()
                        except ValueError:
                            raise ValidationError(
                                {"payperiod": f"Invalid date format in {source_col}: {value}"}
                            )

                        row_dict[model_col] = newDate

                        # Find pay period
                        # Aquired from input date
                        payPeriodModel = apps.get_model('WCHDApp', 'PayPeriod')
                        periods = payPeriodModel.objects.all()

                        for period in periods:
                            if period.periodStart <= newDate <= period.periodEnd:
                                row_dict["payperiod"] = period
                                break
                    else:
                        row_dict[model_col] = value

                row_dict["startTime"] = startTimeHour
                data.append(row_dict)

            try:
                with transaction.atomic():
                    for line in data:
                        if 'payperiod' not in line:
                            raise ValidationError({"payperiod": "No payperiod for this date range"})

                        # Convert types
                        for key in list(line.keys()):
                            if isinstance(line[key], np.integer):
                                line[key] = int(line[key])
                            elif isinstance(line[key], np.floating):
                                line[key] = float(line[key])

                        # Foreign keys
                        for key in list(line.keys()):
                            if key not in fks:
                                continue

                            parentModel = apps.get_model('WCHDApp', key)

                            if key == "employee":
                                full_name = str(line[key]).strip()

                                # Remove after comma
                                full_name = full_name.split(",")[0].strip()

                                parts = full_name.split()
                                if len(parts) == 0:
                                    raise ValidationError({"employee": "Employee name is blank"})

                                first_name = parts[0]
                                surname = parts[-1] if len(parts) > 1 else None

                                if surname:
                                    matches = parentModel.objects.filter(
                                        first_name__iexact=first_name,
                                        surname__iexact=surname
                                    )
                                else:
                                    matches = parentModel.objects.filter(
                                        first_name__iexact=first_name
                                    )

                                if matches.count() == 0 and len(parts) > 1:
                                    # Fallback: first name only
                                    matches = parentModel.objects.filter(
                                        first_name__iexact=first_name
                                    )

                                if matches.count() == 0:
                                    raise ValidationError(
                                        {"employee": f"No employee found for {full_name}"}
                                    )
                                elif matches.count() > 1:
                                    raise ValidationError(
                                        {"employee": f"Multiple employees matched {full_name}"}
                                    )

                                line[key] = matches.first()

                            elif key == "ActivityList":
                                project_value = str(line[key]).strip()

                                try:
                                    line[key] = parentModel.objects.get(program=project_value)
                                except parentModel.DoesNotExist:
                                    raise ValidationError(
                                        {"ActivityList": f"No ActivityList found for project {project_value}"}
                                    )
                                except parentModel.MultipleObjectsReturned:
                                    raise ValidationError(
                                        {"ActivityList": f"Multiple ActivityList rows found for project {project_value}"}
                                    )

                            elif key == "dept":
                                try:
                                    line[key] = parentModel.objects.get(dept_name=line[key])
                                except parentModel.DoesNotExist:
                                    raise ValidationError({"dept": "Department does not exist"})
                                except parentModel.MultipleObjectsReturned:
                                    raise ValidationError({"dept": "Multiple departments matched"})

                        activity = line['ActivityList']
                        paidEmployee = line['employee']

                        payType = activity.payType
                        if payType == "special":
                            item = paidEmployee.specialPayItem
                        elif payType == "admin":
                            item = paidEmployee.payItem
                        else:
                            item = activity.item

                        payRate = Decimal(str(paidEmployee.pay_rate))
                        hours = Decimal(str(line["hours"]))

                        amount = payRate * hours
                        amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                        # Match people
                        try:
                            people = People.objects.get(
                                name=f"{paidEmployee.first_name} {paidEmployee.surname}".strip()
                            )
                        except People.DoesNotExist:
                            raise ValidationError(
                                {"people": f"No People object found for {paidEmployee.first_name} {paidEmployee.surname}"}
                            )
                        except People.MultipleObjectsReturned:
                            raise ValidationError(
                                {"people": f"Multiple People objects found for {paidEmployee.first_name} {paidEmployee.surname}"}
                            )

                        expenseFullID = (
                            f"{paidEmployee.employee_id}-"
                            f"{activity.ActivityList_id}-"
                            f"{line['beg_date']}-"
                            f"{line['startTime']}"
                        )

                        duplicate = Expense.objects.filter(expenseFullID=expenseFullID).exists()

                        if not duplicate:
                            if dateInputted == "":
                                expense = Expense(
                                    item=item,
                                    amount=amount,
                                    people=people,
                                    warrant=1,
                                    comment="Payroll",
                                    ActivityList=activity,
                                    line=item.line,
                                    employee=paidEmployee,
                                    expenseFullID=expenseFullID
                                )
                            else:
                                expense = Expense(
                                    item=item,
                                    date=dateInputted,
                                    amount=amount,
                                    people=people,
                                    warrant=1,
                                    comment="Payroll",
                                    ActivityList=activity,
                                    line=item.line,
                                    employee=paidEmployee,
                                    expenseFullID=expenseFullID
                                )

                            expense.full_clean()
                            expense.save()
                            message = "Posted"

                        # Only used for duplicates
                        line.pop("startTime", None)

                        if "pay_amount" in line and line["pay_amount"] is not None:
                            line["pay_amount"] = Decimal(str(line["pay_amount"])).quantize(
                                Decimal("0.01"),
                                rounding=ROUND_HALF_UP
                            )

                        if "hours" in line and line["hours"] is not None:
                            line["hours"] = Decimal(str(line["hours"])).quantize(
                                Decimal("0.01"),
                                rounding=ROUND_HALF_UP
    )

                        payrollModel.objects.update_or_create(
                            **line,
                            defaults=line
                        )

            except ValidationError as e:
                message = e.message_dict
                if message.get("warrant"):
                    message = message['warrant'][0]
                elif message.get("item"):
                    message = message['item'][0]
                elif message.get("amount"):
                    message = message['amount'][0]
                elif message.get("comment"):
                    message = message['comment'][0]
                elif message.get("ActivityList"):
                    message = message['ActivityList'][0]
                elif message.get("people"):
                    message = message['people'][0]
                elif message.get("employee"):
                    message = message['employee'][0]
                elif message.get("payperiod"):
                    message = message['payperiod'][0]
                elif message.get("dept"):
                    message = message['dept'][0]
            except Exception as e:
                message = f"Import failed: {e}"
    else:
        form = FileInput()

    return render(
        request,
        "WCHDApp/clockifyImportPayroll.html",
        {"form": form, "message": message}
    )

def calculateActivitySelect(request, *args, **kwargs):
    payrollModel = apps.get_model('WCHDApp', 'Payroll')
    payperiodGroup = request.GET.get('payperiodDropdown')
    print(payperiodGroup)
    if payperiodGroup == None:
        data = payrollModel.objects.all()
    else:
        data = payrollModel.objects.filter(payperiod=payperiodGroup)
    #for obj in data:
        #print(obj.ActivityList.fund)

    #print(data)
    fields = []
    verboseNames = []
    for field in payrollModel._meta.get_fields():
        if field.is_relation:
            #Grab related model. This is why foreign keys have to be named after the model 
            parentModel = apps.get_model('WCHDApp', field.name)

            #Get the related models primary key
            fkName = parentModel._meta.pk.name
            verboseNames.append(parentModel._meta.pk.verbose_name)
            fields.append(fkName)
        else:
            verboseNames.append(field.verbose_name)
            fields.append(field.name)

    #Making the dropdowns for selecting the fund, activity, and employee
    activityModel = apps.get_model('WCHDApp', 'ActivityList')
    activities = activityModel.objects.all()
    activityChoices = []
    for activity in activities:
        activityChoices.append((activity.ActivityList_id, activity.program))
    
    employeeModel = apps.get_model("WCHDApp", "employee")
    employees = employeeModel.objects.all()
    employeeChoices = []
    for employee in employees:
        employeeChoices.append((employee.employee_id, employee.first_name))

    fundModel = apps.get_model("WCHDApp", "fund")
    funds = fundModel.objects.all()
    fundChoices = []
    for fund in funds:
        fundChoices.append((fund.fund_id, fund.fund_name))

    payperiodModel = apps.get_model("WCHDApp", "PayPeriod")
    payperiods = payperiodModel.objects.all()
    payperiodChoices = []
    for payperiod in payperiods:
        payperiodChoices.append(payperiod.payperiod_id)
    
    context = {
        "activityChoices": activityChoices,
        "employeeChoices": employeeChoices,
        "fundChoices": fundChoices,
        "payperiodChoices": payperiodChoices,
        "data": data, 
        "fields": fields, 
        "verboseFields": verboseNames}

    return render(request, "WCHDApp/calculateActivitySelect.html", context)

def getActivities(request):
    #This is used to have an array of the activities in javascript
    activityModel = apps.get_model('WCHDApp', 'ActivityList')
    activities = activityModel.objects.all()
    activityChoices = []
    for activity in activities:
        activityChoices.append((activity.ActivityList_id, activity.program))
    
    data = {
        "activities": activityChoices
    }
    return JsonResponse(data)

def payrollView(request, *args, **kwargs):
    payperiodModel = apps.get_model("WCHDApp", "PayPeriod")
    payperiods = payperiodModel.objects.all()
    payperiodChoices = []
    for payperiod in payperiods:
        payperiodChoices.append(payperiod.payperiod_id)

    activityModel = apps.get_model('WCHDApp', 'ActivityList')
    activities = activityModel.objects.all()
    activityChoices = []
    for activity in activities:
        activityChoices.append((activity.ActivityList_id, activity.program))
    
    employeeModel = apps.get_model("WCHDApp", "employee")
    employees = employeeModel.objects.all()
    employeeChoices = []
    for employee in employees:
        employeeChoices.append((employee.employee_id, employee.first_name))

    fundModel = apps.get_model("WCHDApp", "fund")
    funds = fundModel.objects.all()
    fundChoices = []
    for fund in funds:
        fundChoices.append((fund.fund_id, fund.fund_name))
    
    context = {
        "payperiodChoices": payperiodChoices,
        "activityChoices": activityChoices,
        "fundChoices": fundChoices,
        "employeeChoices": employeeChoices,
        }

    return render(request, "WCHDApp/payrollView.html", context)

def fundSummary(request):
    fundID = request.GET.get("fundDropdown")
    payperiodID = request.GET.get('payperiodDropdown')
    if fundID != "EMPTY":
        fund = apps.get_model("WCHDApp", "fund")
        selectedFund = fund.objects.get(fund_id=fundID)
        fundName = selectedFund.fund_name

        payrollModel = apps.get_model('WCHDApp', 'Payroll')
        #Have to use double underscore instead of dot here for whatever reason
        filteredRows = payrollModel.objects.filter(ActivityList__fund__fund_id=fundID, payperiod__payperiod_id=payperiodID)

        totalPay = 0
        totalHours = 0
        for row in filteredRows:
            totalPay += row.pay_amount
            totalHours += row.hours

        context = {
            "specifiedField": "Fund Name",
            "specifiedValue": fundName,
            "sum": totalPay,
            "totalHours": totalHours
        }
        
        return render(request, "WCHDApp/partials/totalsOutput.html", context)
    else:
        return HttpResponse("No Fund selected", status=204)

def activitySummary(request):
    activityID = request.GET.get("activityDropdown")
    payperiodID = request.GET.get('payperiodDropdown')
    if activityID != "EMPTY":
        activity = apps.get_model("WCHDApp", "ActivityList")
        selectedActivity = activity.objects.get(ActivityList_id=activityID)
        activityName = selectedActivity.program

        payrollModel = apps.get_model('WCHDApp', 'Payroll')
        #Have to use double underscore instead of dot here for whatever reason
        filteredRows = payrollModel.objects.filter(ActivityList__ActivityList_id=activityID, payperiod__payperiod_id=payperiodID)

        totalPay = 0
        totalHours = 0
        for row in filteredRows:
            totalPay += row.pay_amount
            totalHours += row.hours

        context = {
            "specifiedField": "Activity Name",
            "specifiedValue": activityName,
            "sum": totalPay,
            "totalHours": totalHours
        }
        
        return render(request, "WCHDApp/partials/totalsOutput.html", context)
    else:
        return HttpResponse("No Activity selected", status=204)

def employeeSummary(request):
    employeeID = request.GET.get("employeeDropdown")
    payperiodID = request.GET.get('payperiodDropdown')
    if employeeID != "EMPTY":
        employee = apps.get_model("WCHDApp", "Employee")
        selectedEmployee = employee.objects.get(employee_id=employeeID)
        employeeName = selectedEmployee.first_name + " " + selectedEmployee.surname

        payrollModel = apps.get_model('WCHDApp', 'Payroll')
        #Have to use double underscore instead of dot here for whatever reason
        filteredRows = payrollModel.objects.filter(employee__employee_id=employeeID, payperiod__payperiod_id=payperiodID)

        totalPay = 0
        totalHours = 0
        for row in filteredRows:
            totalPay += row.pay_amount
            totalHours += row.hours

        activityModel = apps.get_model("WCHDApp", "ActivityList")
        activities = activityModel.objects.all()

        activitiesDict = {}
        for activity in activities:
            activityFilteredRows = payrollModel.objects.filter(ActivityList=activity, payperiod__payperiod_id=payperiodID, employee__employee_id=employeeID)
            activityPay = 0
            activityHours = 0
            for activityRow in activityFilteredRows:
                activityPay += activityRow.pay_amount
                activityHours += activityRow.hours
            
            activitiesDict[activity.program] = {"name":activity.program, "sum":activityPay, "hours":activityHours}

        context = {
            "employeeName": employeeName,
            "activitiesDict": activitiesDict,
            "sum": totalPay,
            "totalHours": totalHours
        }
        
        return render(request, "WCHDApp/partials/employeeBreakdown.html", context)
    else:
        return HttpResponse("No Employee selected", status=204)

def transactionCustomView(request):
    return render(request, "WCHDApp/transactionCustomView.html")

def grantStats(request):
    grantModel = apps.get_model("WCHDApp", "Grant")
    grants = grantModel.objects.all()

    grantLineModel = apps.get_model("WCHDApp", "GrantLine")

    #Going to be a list of dictionaries. Each grant will have a dictionary
    grantList = []

    for grant in grants:
        grantLines = grantLineModel.objects.filter(grant = grant)

        totalBudgeted = 0
        totalSpent = 0
        totalRemaining = 0
        for grantLine in grantLines:
            totalRemaining += float(grantLine.budgetRemaining)
            totalSpent += float(grantLine.budgetSpent)
            totalBudgeted += float(grantLine.line_budgeted)

        grantDict = {
            "grantID": grant.grant_id,
            "grantName": grant.grant_name,
            "awardAmount": f"${grant.award_amount:,.2f}",
            "spent": f"${totalSpent:,.2f}",
            "remaining": f"${totalRemaining:,.2f}",
            "budgeted": f"${totalBudgeted:,.2f}",
            "received": f"${grant.received:,.2f}",
        }

        grantList.append(grantDict)

    context = {
        "grantList": grantList
    }
    return render(request, "WCHDApp/grantStats.html", context)

def grantBreakdown(request):
    grantID = request.GET.get("grantID")

    grantModel = apps.get_model("WCHDApp", "Grant")
    grant = grantModel.objects.get(pk=grantID)

    grantLineModel = apps.get_model("WCHDApp", "GrantLine")
    grantLines = grantLineModel.objects.filter(grant__grant_id=grantID)

    linesList = []
    total = 0
    for line in grantLines:
        total += line.line_budgeted
        lineDict = {
            "lineName": line.line_name,
            "budgeted": line.line_budgeted,
            "remaining": line.budgetRemaining,
            "spent": line.budgetSpent,
            "income": line.totalIncome
        }
        linesList.append(lineDict)

    unbudgeted = grant.award_amount - total

    context = {
        "linesList": linesList,
        "unbudgeted": unbudgeted
    }

    return render(request, "WCHDApp/partials/grantBreakdownTable.html", context)

def grantLineView(request):
    grants = Grant.objects.all()
    
    context = {
        "grants": grants
    }
    return render(request, "WCHDApp/grantLineView.html", context)

def grantLineTableUpdate(request):
    message = ""
    grantID = request.GET.get("grant")
    grant = Grant.objects.get(pk=grantID)

    grantLines = GrantLine.objects.filter(grant=grant)

    fields = GrantLine._meta.fields

    fieldNames = []
    decimalFields = []
    aliasNames = []

    calculatedProperties = {
        "GrantLine": [
            ("budgetRemaining", "Budget Remaining"),
            ("budgetSpent", "Budget Spent"),
            ("totalIncome", "Total Income"),
        ]
    }

    for field in fields:
        if isinstance(field, DecimalField):
            decimalFields.append(field.name)
        aliasNames.append(field.verbose_name)
        fieldNames.append(field.name)

    if "GrantLine" in calculatedProperties:
        for prop_name, prop_label in calculatedProperties["GrantLine"]:
            aliasNames.append(prop_label)
            fieldNames.append(prop_name)
            decimalFields.append(prop_name)

    if request.method == "POST":
        form = modelform_factory(GrantLine, exclude=["grant", "fund_year"])(request.POST)
        form.instance.grant = grant
        form.instance.fund_year = grant.fund.fund_id.split("-")[0]

        if form.is_valid():
            form.save()
            message = "Grant Line Created Successfully"
            form = modelform_factory(GrantLine, exclude=["grant", "fund_year"])()
        else:
            errors = form.errors
            if errors.get("line_budgeted"):
                message = errors["line_budgeted"][0]
            if errors.get("lineType"):
                message = errors["lineType"][0]
    else:
        form = modelform_factory(GrantLine, exclude=["grant", "fund_year"])()

    grantLines = GrantLine.objects.filter(grant=grant)

    total_budget_remaining = Decimal("0.00")
    total_budget_spent = Decimal("0.00")
    total_income = Decimal("0.00")

    for gl in grantLines:
        total_budget_remaining += gl.budgetRemaining
        total_budget_spent += gl.budgetSpent
        total_income += gl.totalIncome

    context = {
        "fields": fieldNames,
        "aliasNames": aliasNames,
        "data": grantLines,
        "decimalFields": decimalFields,
        "form": form,
        "grant": grant,
        "message": message,
        "grantAwardAmountRemaining": grant.grantAwardAmountRemaining,

        # totals under the table
        "total_budget_remaining": total_budget_remaining,
        "total_budget_spent": total_budget_spent,
        "total_income": total_income,
    }

    return render(request, "WCHDApp/partials/grantLineTableUpdate.html", context)

def testingGrantAccess(request):
    grantModel = apps.get_model("WCHDApp", "Grant")
    grants = grantModel.objects.all()
    context ={
        "grants": grants
    }

    fields = grantModel._meta.get_fields()
    print(fields)
    for field in fields:
        #if not field.auto_created or not isinstance(field, AutoField) or not field.is_relation:
        if not field.auto_created:
            print(field.name)
            if isinstance(field, ManyToManyField):
                print("Many to many field")
                print(grants[0].fund.all())
            else:
                print(getattr(grants[0], field.name))


    relatedFunds = grants[0].fund.all()
    print(relatedFunds)
    context = {
        "funds": relatedFunds
    }
    #making change
    return render(request, "WCHDApp/grantExpenseTesting.html", context)

def viewByYear(request):
    currentDate = datetime.now()
    year = currentDate.year
    years = list(range(2000, year+2))

    models = ["Fund", "Line", "Item", "Revenue", "GrantLine", "Testing", "Payroll"]

    context = {
        "years": years,
        "models": models
    }

    return render(request, "WCHDApp/viewByYear.html", context)

def viewByYearPartial(request):
    message = ""
    #Any property that we define in models need to go here so our logic can include them in the table
    calculatedProperties = {
        "Testing": [("fundBalanceMinus3", "Fund Balance Minus 3")],
        "Payroll": [("pay_rate", "Pay Rate")],
        "Fund":[("calcRemaining", "Remaining")]
    }

    #Requests come in as both get and post request whether it is the form being submitted or the htmx triggering the rendering
    modelName = request.GET.get('model') or request.POST.get('model')
    year = request.GET.get("yearDropdown") or request.POST.get("yearDropdown")
    model = apps.get_model('WCHDApp', modelName)
    if modelName == "Fund":
        values = Fund.objects.filter(fund_id__startswith=year)
        fields = Fund._meta.fields 
        if request.method == "POST":
            form = modelform_factory(model, exclude=["fund_total"])(request.POST)
            if form.is_valid():
                fund = form.save()
                message = "Fund Created"
                form = modelform_factory(model, exclude=["fund_total"])()
        else:
            form = modelform_factory(model, exclude=["fund_total"])()
    if modelName == "Line":
        values = Line.objects.filter(fund__fund_id__startswith=year)
        fields = Line._meta.fields
        if request.method == 'POST':
            form = modelform_factory(Line, exclude=["fund_year"])(request.POST)
            if form.is_valid():
                line = form.save()
                message = "Line created successfully"
                form = modelform_factory(Line, exclude=["fund_year"])()
            else:
                errors = form.errors
                if errors.get("line_budgeted"):
                    message = errors["line_budgeted"][0]     
        else:
            form = modelform_factory(Line, exclude=["fund_year"])()
    if modelName == "Item":
        values = Item.objects.filter(line__fund__fund_id__startswith=year)
        fields = Item._meta.fields
        if request.method == 'POST':
            form = modelform_factory(Item, exclude=["fund", "fund_year", "fund_type"])(request.POST)
        
            if form.is_valid():
                item = form.save()
                message = "Item Created Successfully"
                form = modelform_factory(Item, exclude=["fund", "fund_year", "fund_type"])()
            else:
                errors = form.errors
                if errors.get("line_budgeted"):
                    message = errors["line_budgeted"][0]     
                if errors.get("lineType"):
                    message = errors["lineType"][0]           
        else:
            form = modelform_factory(Item, exclude=["fund", "fund_year", "fund_type"])()
        

    fieldNames = []
    aliasNames = []
    decimalFields = []
    for field in fields:
        if isinstance(field, DecimalField):
                decimalFields.append(field.name)
        aliasNames.append(field.verbose_name)  
        fieldNames.append(field.name)
    #Making sure properties are added like normal fields to the tables
    if modelName in calculatedProperties:
        for property in calculatedProperties[modelName]:
            #print(property)
            aliasNames.append(property[1])
            fieldNames.append(property[0])
            decimalFields.append(property[0])

    context = {"fields": fieldNames, 
               "aliasNames": aliasNames, 
               "data": values, 
               "tableName": modelName, 
               "decimalFields": decimalFields,
               "form": form,
               "year":year,
               "message": message}

    return render(request, "WCHDApp/partials/viewByYearPartial.html", context)


#Might be onto something with this. Cut down on repetition
def testingTableViewFunction(request, tableName):
    #Grabbing the model selected in viewTableSelect
    model = apps.get_model('WCHDApp', tableName)

    #Getting data from that model
    values = model.objects.all()

    #Getting just field names from model
    #Use .fields instead of .get_fields() because we do not want reverse relationships
    fields = model._meta.fields

    #Any property that we define in models need to go here so our logic can include them in the table
    calculatedProperties = {
        "Testing": [("fundBalanceMinus3", "Fund Balance Minus 3")],
        "Payroll": [("pay_rate", "Pay Rate")],
        "Fund":[("calcRemaining", "Remaining"), ("budgeted", "Budgeted")],
        "GrantLine": [("budgetRemaining", "Budget Remaining"), ("budgetSpent", "Budget Spent"), ("totalIncome", "Total Income")],
        "Grant": [("grantAwardAmountRemaining", "Grant Award Amount Remaining"),( "recieved","Recieved")]
    }

    #This is used to decide which fields we want to show in the accumulator based on each model
    summedFields = {
        "Fund": "fund_cash_balance", 
        "Line": "line_total_income",
        "Transaction": "amount",
    }
    

    fieldNames = []
    aliasNames = []
    decimalFields = []
    for field in fields:
        if isinstance(field, DecimalField):
                decimalFields.append(field.name)
        aliasNames.append(field.verbose_name)  
        fieldNames.append(field.name)
    #Making sure properties are added like normal fields to the tables
    if tableName in calculatedProperties:
        for property in calculatedProperties[tableName]:
            #print(property)
            aliasNames.append(property[1])
            fieldNames.append(property[0])
            decimalFields.append(property[0])

    #Getting values based on if we defined them in summedFields in order to make accumulator
    if tableName in summedFields:
        field = summedFields[tableName]
        accumulator = 0
        for value in values:
            accumulator += getattr(value, field)
        context = {"fields": fieldNames, "aliasNames": aliasNames, "data": values, "tableName": tableName, "decimalFields": decimalFields, "accumulator": accumulator}
    else:
        context = {"fields": fieldNames, "aliasNames": aliasNames, "data": values, "tableName": tableName, "decimalFields": decimalFields}

    return [fieldNames, aliasNames, decimalFields]


def updateRevenues(request):
    revenues = Revenue.objects.all()
    for revenue in revenues:
        revenue.reference = 1
        revenue.save()
    print("Updated")
    return render(request, "WCHDApp/testing.html")

def projection_chart(request):

    result = None
    result_image = None
    form = ProjectionCalcForm()
    labels = None
    values = None

    if request.method == "POST":
        form = ProjectionCalcForm(request.POST)
        if form.is_valid():
            employee_id = form.cleaned_data['employee_id']
            employee = Employee.objects.get(employee_id=employee_id)
            request.session["employee_id"] = employee.employee_id
            salary = float(employee.pay_rate * 40 * 52)
            workersComp = salary * float(0.01)
            medicare = salary * float(0.0145)
            opers = salary * float(0.14)
            expense = salary + workersComp + medicare + opers
            result = (
                f"Estimated expense for this employee:\n"
                f"Salary: ${salary:,.2f}\n"
                f"OPERS: ${opers:,.2f}\n"
                f"Medicare: ${medicare:,.2f}\n"
                f"Workers Comp: ${workersComp:,.2f}\n"
                f"Total: ${expense:,.2f}"
            )

            fig, ax = plt.subplots()

            components = ["Salary", "OPERS", "Medicare", "Workers Comp"]
            values = [salary, opers, medicare, workersComp]

            colors = ["#4CAF50", "#2196F3", "#FF9800", "#F44336"]

            bottom = 0
            for i in range(len(values)):
                ax.bar("Total Expense", values[i], bottom=bottom, label=components[i], color=colors[i])
                bottom += values[i]

            ax.set_title("Expense Breakdown")

            def money(x, pos):
                return f'${x:,.0f}'

            ax.yaxis.set_major_formatter(FuncFormatter(money))
            ax.legend()

            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            buf.seek(0)

            image_base64 = base64.b64encode(buf.getvalue()).decode()

            result_image = image_base64
    else:
        print("Invalid form submission")
    return render(request, "WCHDApp/projections.html", {"form": form, "result": result, "labels": labels, "values": values, "result_image": result_image})

# hello

def projectionPage(request):
    return render(request, "WCHDApp/projections.html")

def insuranceAssignmentView(request):
    return render(request, "WCHDApp/insuranceAssignmentView.html")

def insuranceAssignmentTableUpdate(request):
    message = ""

    insuranceAssignmentModel = apps.get_model('WCHDApp', "InsuranceAssignment")
    insuranceAssignmentValues = insuranceAssignmentModel.objects.all().order_by("year", "employee")

    fields = [field for field in insuranceAssignmentModel._meta.fields if field.name != "id"]

    fieldNames = []
    decimalFields = []
    aliasNames = []

    for field in fields:
        if isinstance(field, DecimalField):
            decimalFields.append(field.name)
        aliasNames.append(field.verbose_name)
        fieldNames.append(field.name)

    insuranceAssignmentForm = modelform_factory(
        insuranceAssignmentModel,
        exclude=[],
        widgets={
            "employee": forms.Select(attrs={"class": "searchable-select"}),
        }
    )

    if request.method == "POST":
        form = insuranceAssignmentForm(request.POST)
        if form.is_valid():
            form.save()
            message = "Insurance assignment posted successfully"
            form = insuranceAssignmentForm()
            insuranceAssignmentValues = insuranceAssignmentModel.objects.all().order_by("year", "employee")
        else:
            message = "Please correct the errors below."
    else:
        form = insuranceAssignmentForm()

    context = {
        "fields": fieldNames,
        "aliasNames": aliasNames,
        "data": insuranceAssignmentValues,
        "decimalFields": decimalFields,
        "form": form,
        "message": message,
    }

    return render(request, "WCHDApp/partials/insuranceAssignmentTablePartial.html", context)

def insuranceHome(request):
    return render(request, "WCHDApp/insuranceHome.html")

def insurancePercentageView(request):
    return render(request, "WCHDApp/insurancePercentageView.html")

def insurancePercentageTableUpdate(request):
    message = ""

    insurancePercentageModel = apps.get_model('WCHDApp', "InsurancePercentage")
    insurancePercentageValues = insurancePercentageModel.objects.all().order_by("start_date", "end_date", "employee", "fund")

    fields = [field for field in insurancePercentageModel._meta.fields if field.name != "id"]

    fieldNames = []
    decimalFields = []
    aliasNames = []

    for field in fields:
        if isinstance(field, DecimalField):
            decimalFields.append(field.name)
        aliasNames.append(field.verbose_name)
        fieldNames.append(field.name)

    insurancePercentageForm = modelform_factory(
        insurancePercentageModel,
        exclude=[],
        widgets={
            "person": forms.Select(attrs={"class": "searchable-select"}),
            "fund": forms.Select(attrs={"class": "searchable-select"}),
        }
    )

    if request.method == "POST":
        form = insurancePercentageForm(request.POST)
        if form.is_valid():
            form.save()
            message = "Insurance percentage posted successfully"
            form = insurancePercentageForm()
            insurancePercentageValues = insurancePercentageModel.objects.all().order_by("start_date", "end_date", "employee", "fund")
        else:
            message = "Please correct the errors below."
    else:
        form = insurancePercentageForm()

    context = {
        "fields": fieldNames,
        "aliasNames": aliasNames,
        "data": insurancePercentageValues,
        "decimalFields": decimalFields,
        "form": form,
        "message": message,
    }

    return render(request, "WCHDApp/partials/insurancePercentageTablePartial.html", context)


def getFundFromProject(projectName):
    if not projectName:
        return None

    projectName = " ".join(str(projectName).strip().split())

    activity = ActivityList.objects.filter(program__iexact=projectName).select_related("fund").first()
    if activity:
        return activity.fund

    return None

def getEmployeeFromClockifyName(userName):
    if not userName:
        return None

    cleanedUserName = " ".join(str(userName).strip().split()).lower()

    for employee in Employee.objects.all():
        employeeName = f"{employee.first_name} {employee.surname}"
        employeeName = " ".join(employeeName.strip().split()).lower()

        if employeeName == cleanedUserName:
            return employee

    return None


def getMonthDateRange(year, month):
    lastDay = calendar.monthrange(year, month)[1]
    monthStart = date(year, month, 1)
    monthEnd = date(year, month, lastDay)
    return monthStart, monthEnd


def generateInsuranceAllocations(year, month):
    monthStart, monthEnd = getMonthDateRange(year, month)

    assignments = InsuranceAssignment.objects.filter(
        year=year,
        employee__isnull=False
    ).select_related("employee")

    for assignment in assignments:
        employee = assignment.employee

        percentageRows = InsurancePercentage.objects.filter(
            employee=employee,
            start_date__lte=monthEnd,
            end_date__gte=monthStart,
        ).select_related("fund")

        for row in percentageRows:
            multiplier = Decimal(str(row.percent_of_time)) / Decimal("100.00")

            healthAmount = (assignment.health_rate * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            dentalAmount = (assignment.dental_rate * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            lifeAmount = (assignment.life_rate * multiplier).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            InsuranceAllocation.objects.update_or_create(
                year=year,
                month=month,
                employee=employee,
                fund=row.fund,
                defaults={
                    "percent_of_time": row.percent_of_time,
                    "health": healthAmount,
                    "dental": dentalAmount,
                    "life": lifeAmount,
                }
            )

def rebuildInsuranceAllocations(year, month):
    InsuranceAllocation.objects.filter(year=year, month=month).delete()
    generateInsuranceAllocations(year, month)

def processInsurancePercentageImport(selectedFile):
    file = pd.read_csv(selectedFile)

    requiredColumns = ["User", "Project", "Start Date", "End Date", "Duration (decimal)"]
    missingColumns = [col for col in requiredColumns if col not in file.columns]

    if missingColumns:
        return False, f"Missing required columns: {', '.join(missingColumns)}"

    grouped = defaultdict(lambda: {
        "total_hours": Decimal("0.00"),
        "fund_hours": defaultdict(lambda: Decimal("0.00")),
        "start_date": None,
        "end_date": None,
        "employee": None,
        "fund_objects": {},
    })

    skippedRows = []

    for _, row in file.iterrows():
        userName = row["User"]
        projectName = row["Project"]
        durationValue = row["Duration (decimal)"]

        try:
            startDate = pd.to_datetime(row["Start Date"]).date()
            endDate = pd.to_datetime(row["End Date"]).date()
            duration = Decimal(str(durationValue))
        except Exception:
            skippedRows.append(f"Bad date or duration for user {userName}, project {projectName}")
            continue

        employee = getEmployeeFromClockifyName(userName)
        if not employee:
            skippedRows.append(f"No employee match for user: {userName}")
            continue

        fund = getFundFromProject(projectName)
        if not fund:
            skippedRows.append(f"No fund match for project: {projectName}")
            continue

        employeeKey = employee.pk
        grouped[employeeKey]["employee"] = employee
        grouped[employeeKey]["total_hours"] += duration
        grouped[employeeKey]["fund_hours"][fund.pk] += duration
        grouped[employeeKey]["fund_objects"][fund.pk] = fund

        if grouped[employeeKey]["start_date"] is None or startDate < grouped[employeeKey]["start_date"]:
            grouped[employeeKey]["start_date"] = startDate

        if grouped[employeeKey]["end_date"] is None or endDate > grouped[employeeKey]["end_date"]:
            grouped[employeeKey]["end_date"] = endDate

    createdCount = 0
    allocationPeriods = set()

    for _, info in grouped.items():
        employee = info["employee"]
        totalHours = info["total_hours"]
        startDate = info["start_date"]
        endDate = info["end_date"]

        if totalHours == 0:
            continue

        if startDate:
            allocationPeriods.add((startDate.year, startDate.month))
        if endDate:
            allocationPeriods.add((endDate.year, endDate.month))

        for fundId, fundHours in info["fund_hours"].items():
            fund = info["fund_objects"][fundId]
            percent = (fundHours / totalHours) * Decimal("100.00")
            percent = percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            InsurancePercentage.objects.update_or_create(
                employee=employee,
                fund=fund,
                start_date=startDate,
                end_date=endDate,
                defaults={
                    "percent_of_time": percent,
                }
            )
            createdCount += 1

    for year, month in allocationPeriods:
        rebuildInsuranceAllocations(year, month)

    if skippedRows:
        print("Skipped rows:")
        for row in skippedRows:
            print(row)
        return True, f"Imported {createdCount} insurance percentage rows and updated insurance allocations. Some rows were skipped."

    return True, f"Imported {createdCount} insurance percentage rows and updated insurance allocations successfully."

def getFormattedFundCode(fund):
    return f"{fund.year} {str(fund.fund_id).zfill(4)}"

def getProgramNameFromFund(fund):
    activity = ActivityList.objects.filter(fund=fund).order_by("program").first()
    if activity:
        return activity.program
    return f"{fund.year} {str(fund.fund_id).zfill(4)}"

def getInsuranceReportItem(fund):
    item = Item.objects.filter(
        fund=fund,
        fund_year=fund.year,
        item_name__iexact="Premium Payment"
    ).select_related("line").first()

    if item:
        return item

    return Item.objects.filter(
        fund=fund,
        fund_year=fund.year
    ).select_related("line").first()

def getInsuranceAmount(row, insuranceType):
    if insuranceType == "health":
        return row.health or Decimal("0.00")
    if insuranceType == "dental":
        return row.dental or Decimal("0.00")
    return (row.health or Decimal("0.00")) + (row.dental or Decimal("0.00"))

def buildInsuranceByFund(year, month, insuranceType):
    allocations = InsuranceAllocation.objects.filter(
        year=year,
        month=month
    ).select_related("fund", "employee").order_by("fund", "employee")

    grouped = defaultdict(lambda: {
        "fund": None,
        "fund_code": "",
        "premium_payment": Decimal("0.00"),
        "budget_available": Decimal("0.00"),
        "cash_balance": Decimal("0.00"),
        "rows": [],
    })

    for row in allocations:
        fund = row.fund
        fundId = fund.pk
        rowTotal = getInsuranceAmount(row, insuranceType)

        item = getInsuranceReportItem(fund)
        line = item.line if item else None

        grouped[fundId]["fund"] = fund
        grouped[fundId]["fund_code"] = f"{fund.year} {str(fund.fund_id).zfill(4)}"
        grouped[fundId]["premium_payment"] += rowTotal
        grouped[fundId]["cash_balance"] = fund.fund_cash_balance

        if line:
            grouped[fundId]["budget_available"] = line.budgetRemaining

        grouped[fundId]["rows"].append({
            "employee": str(row.employee),
            "total": rowTotal,
        })

    return list(grouped.values())


def buildInsuranceByEmployee(year, month, insuranceType):
    allocations = InsuranceAllocation.objects.filter(
        year=year,
        month=month
    ).select_related("fund", "employee").order_by("employee", "fund")

    grouped = defaultdict(lambda: {
        "employee": None,
        "grand_total": Decimal("0.00"),
        "rows": [],
    })

    for row in allocations:
        rowTotal = getInsuranceAmount(row, insuranceType)
        employeeId = row.employee.pk

        grouped[employeeId]["employee"] = str(row.employee)
        grouped[employeeId]["grand_total"] += rowTotal
        grouped[employeeId]["rows"].append({
            "program": getProgramNameFromFund(row.fund),
            "total": rowTotal,
        })

    return list(grouped.values())


def buildInsuranceForTrena(year, month, insuranceType):
    allocations = InsuranceAllocation.objects.filter(
        year=year,
        month=month
    ).select_related("fund")

    grouped = defaultdict(lambda: {
        "fund": None,
        "fund_code": "",
        "premium_payment": Decimal("0.00"),
        "budget_available": Decimal("0.00"),
        "cash_balance": Decimal("0.00"),
    })

    for row in allocations:
        fund = row.fund
        fundId = fund.pk
        rowTotal = getInsuranceAmount(row, insuranceType)

        item = getInsuranceReportItem(fund)
        line = item.line if item else None

        grouped[fundId]["fund"] = fund
        grouped[fundId]["fund_code"] = f"{fund.year} {str(fund.fund_id).zfill(4)}"
        grouped[fundId]["premium_payment"] += rowTotal
        grouped[fundId]["cash_balance"] = fund.fund_cash_balance

        if line:
            grouped[fundId]["budget_available"] = line.budgetRemaining

    return list(grouped.values())

@permission_required('WCHDApp.has_full_access', raise_exception=True)
def insuranceReports(request):
    allocationYears = list(
        InsuranceAllocation.objects.order_by("year")
        .values_list("year", flat=True)
        .distinct()
    )

    assignmentYears = list(
        InsuranceAssignment.objects.order_by("year")
        .values_list("year", flat=True)
        .distinct()
    )

    availableYears = sorted(set(allocationYears + assignmentYears))
    if not availableYears:
        availableYears = [date.today().year]

    context = {
        "availableYears": availableYears,
        "months": [
            (1, "January"), (2, "February"), (3, "March"), (4, "April"),
            (5, "May"), (6, "June"), (7, "July"), (8, "August"),
            (9, "September"), (10, "October"), (11, "November"), (12, "December"),
        ]
    }

    if request.method == "POST":
        year = int(request.POST.get("year"))
        month = int(request.POST.get("month"))
        reportType = request.POST.get("report_type")
        insuranceType = request.POST.get("insurance_type")

        return redirect("insuranceReportsPDF", year=year, month=month, report_type=reportType, insurance_type=insuranceType)

    return render(request, "WCHDApp/insuranceReports.html", context)

@permission_required('WCHDApp.has_full_access', raise_exception=True)
def insuranceReportsPDF(request, year, month, report_type, insurance_type):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter))
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Title"],
        fontSize=16,
        spaceAfter=11,
        fontName="Helvetica-Bold"
    )

    table_text_style = ParagraphStyle(
        "TableText",
        parent=styles["Normal"],
        fontSize=7,
        leading=8,
        wordWrap='CJK',
        alignment=0
    )

    header_style = ParagraphStyle(
        "HeaderStyle",
        parent=styles["Normal"],
        fontSize=7,
        leading=8,
        alignment=1,
        fontName="Helvetica-Bold"
    )

    if insurance_type not in ["health", "dental", "all"]:
        insurance_type = "all"
    if insurance_type == "health":
        insuranceLabel = "Health Insurance"
    elif insurance_type == "dental":
        insuranceLabel = "Dental Insurance"
    else:
        insuranceLabel = "Health and Dental Insurance"

    elements.append(Spacer(1, 12))
    elements.append(Paragraph("Washington County Health Department", title_style))
    elements.append(Paragraph(f"{insuranceLabel} for {month:02d}/{year}", styles["Heading2"]))
    elements.append(Spacer(1, 10))


    if report_type == "fund":
        reportData = buildInsuranceByFund(year, month, insurance_type)

        for group in reportData:
            elements.append(
                Paragraph(
                    f"<b>Fund {group['fund_code']}</b> &nbsp;&nbsp; "
                    f"<b>Premium Payment:</b> ${group['premium_payment']:,.2f} &nbsp;&nbsp; "
                    f"<b>Budget Available:</b> ${group['budget_available']:,.2f} &nbsp;&nbsp; "
                    f"<b>Cash Balance:</b> ${group['cash_balance']:,.2f}",
                    styles["Normal"]
                )
            )
            elements.append(Spacer(1, 6))

            data = [[
                Paragraph("Employee", header_style),
                Paragraph("Total Insurance", header_style),
            ]]

            for row in group["rows"]:
                data.append([
                    Paragraph(row["employee"], table_text_style),
                    Paragraph(f'${row["total"]:,.2f}', table_text_style),
                ])

            table = Table(data, colWidths=[4.5*inch, 2.0*inch])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.darkgray),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 12))

        filename = f"insurance_by_fund_{year}_{month:02d}.pdf"

    elif report_type == "employee":
        reportData = buildInsuranceByEmployee(year, month, insurance_type)

        for group in reportData:
            elements.append(Paragraph(f"<b>{group['employee']}</b>", styles["Normal"]))
            elements.append(Spacer(1, 6))

            data = [[
                Paragraph("Program", header_style),
                Paragraph("Total Insurance", header_style),
            ]]

            for row in group["rows"]:
                data.append([
                    Paragraph(row["program"], table_text_style),
                    Paragraph(f'${row["total"]:,.2f}', table_text_style),
                ])

            data.append([
                Paragraph("Grand Total", header_style),
                Paragraph(f'${group["grand_total"]:,.2f}', header_style),
            ])

            table = Table(data, colWidths=[4.5*inch, 2.0*inch])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.darkgray),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("BACKGROUND", (0, 1), (-1, -2), colors.whitesmoke),
                ("BACKGROUND", (0, -1), (-1, -1), colors.lightgrey),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 12))

        filename = f"insurance_by_employee_{year}_{month:02d}.pdf"

    else:
        reportData = buildInsuranceForTrena(year, month, insurance_type)

        data = [[
            Paragraph("Fund", header_style),
            Paragraph("Premium Payment", header_style),
            Paragraph("Budget Available", header_style),
            Paragraph("Cash Balance", header_style),
        ]]

        for group in reportData:
            data.append([
                Paragraph(group["fund_code"], table_text_style),
                Paragraph(f'${group["premium_payment"]:,.2f}', table_text_style),
                Paragraph(f'${group["budget_available"]:,.2f}', table_text_style),
                Paragraph(f'${group["cash_balance"]:,.2f}', table_text_style),
            ])

        table = Table(data, colWidths=[1.5*inch, 1.8*inch, 1.8*inch, 1.8*inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.darkgray),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 1), (-1, -1), colors.whitesmoke),
        ]))
        elements.append(table)

        filename = f"insurance_for_auditor_{year}_{month:02d}.pdf"

        elements.append(Paragraph("340 Muskingum Dr, Suite B, Marietta OH 45750"))

    doc.build(elements)

    buffer.seek(0)
    pdf_data = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf_data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response

@staff_member_required
def downloadAdminLog(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="admin_recent_actions.csv"'

    writer = csv.writer(response)

    writer.writerow([
        "Action Time",
        "User",
        "Action",
        "Model",
        "Object",
        "Object ID",
        "Change Message",
    ])

    logs = LogEntry.objects.select_related(
        "user",
        "content_type"
    ).order_by("-action_time")

    for log in logs:
        writer.writerow([
            log.action_time,
            log.user.username if log.user else "",
            log.get_action_flag_display(),
            log.content_type.model if log.content_type else "",
            log.object_repr,
            log.object_id,
            log.change_message,
        ])

    return response