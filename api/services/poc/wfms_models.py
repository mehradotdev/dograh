from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WfmsModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class CallerProfile(WfmsModel):
    user_type: str = Field(alias="UserType")
    id: int | None = Field(default=None, alias="Id")
    code: str | None = Field(default=None, alias="Code")
    name: str | None = Field(default=None, alias="Name")
    mobile: str | None = Field(default=None, alias="MobileNo")
    email: str | None = Field(default=None, alias="Email")
    department_id: int | None = Field(default=None, alias="DepartmentId")
    department_name: str | None = Field(default=None, alias="DepartmentName")
    designation_name: str | None = Field(default=None, alias="DesignationName")
    designation_id: int | None = Field(default=None, alias="DesignationId")
    branch_id: int | None = Field(default=None, alias="BranchId")
    customer_id: int | None = Field(default=None, alias="CustomerId")


class Ticket(WfmsModel):
    request_id: int = Field(alias="RequestId")
    ticket_number: str = Field(alias="TicketNumber")
    query_title: str | None = Field(default=None, alias="QueryTitle")
    user_name: str | None = Field(default=None, alias="UserName")
    email: str | None = Field(default=None, alias="Email")
    contact_number: str | None = Field(default=None, alias="ContactNumber")
    description: str | None = Field(default=None, alias="Description")
    created_date: str | None = Field(default=None, alias="CreatedDate")
    category_name: str | None = Field(default=None, alias="CategoryName")
    ticket_status: str | None = Field(default=None, alias="TicketStatus")
    status_id: int | None = Field(default=None, alias="StatusID")


class TicketSummaryRow(WfmsModel):
    status_id: int = Field(alias="StatusId")
    ticket_id: int = Field(alias="TicketId")
    status: str = Field(alias="Status")
    remarks: str | None = Field(default=None, alias="Remarks")
    employee_name: str | None = Field(default=None, alias="fvEmployeeName")
    updated_at: str | None = Field(default=None, alias="UpdatedAt")


class TicketDraft(BaseModel):
    query_title: str
    description: str
    issue_type: str
    user_name: str | None = None
    email: str | None = None
    employee_id: str | None = None
    full_address: str | None = None
    caller_type: str | None = None
    category: str | None = None
    subcategory: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class CreateTicketResult(WfmsModel):
    success: bool
    message: str | None = None
    ticket_number: str | None = Field(default=None, alias="ticketNumber")
