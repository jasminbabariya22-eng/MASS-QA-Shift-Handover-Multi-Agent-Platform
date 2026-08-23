import os
import sys
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

load_dotenv()

from app.agents import orchestrator, AgentRequest
from app.db.database import SessionLocal

def print_separator(title=""):
    print("\n" + "="*80)
    if title:
        print(f" {title.upper()} ".center(80, "="))
        print("="*80)

def main():
    print_separator("MASS QA & Shift Handover Platform — Live Agent Demonstration")
    
    session_id = "live-demo-session-101"
    
    # -------------------------------------------------------------
    # Scenario 1: Outgoing Console Operator Creates & Populates Draft
    # -------------------------------------------------------------
    print("\n[STEP 1] Outgoing Console Operator (John) initiates handover:")
    req1 = AgentRequest(
        user_id="op_john_console",
        user_role="CONSOLE_OPERATOR",
        session_id=session_id,
        message="Create a day shift handover for Unit CDU-101"
    )
    res1 = orchestrator.execute(req1)
    print(f"User > {req1.message}")
    print(f"Agent ({res1.agent_id}) >\n{res1.response}")

    # Extract handover number from response metadata if available
    hnum = res1.metadata.get("handover_number", "SHO-20260822-CDU101-0001")

    print("\n[STEP 2] Outgoing Operator logs operational equipment observation:")
    req2 = AgentRequest(
        user_id="op_john_console",
        user_role="CONSOLE_OPERATOR",
        session_id=session_id,
        message=f"Add note that compressor C-101 has high vibration at 4.8 mm/s on Unit CDU-101"
    )
    res2 = orchestrator.execute(req2)
    print(f"User > {req2.message}")
    print(f"Agent ({res2.agent_id}) >\n{res2.response}")

    print("\n[STEP 3] Outgoing Operator attaches a safety-critical LOTO isolation:")
    req3 = AgentRequest(
        user_id="op_john_console",
        user_role="CONSOLE_OPERATOR",
        session_id=session_id,
        message=f"Add LOTO safety item tag P-101A pump isolated for mechanical seal replacement on Unit CDU-101"
    )
    res3 = orchestrator.execute(req3)
    print(f"User > {req3.message}")
    print(f"Agent ({res3.agent_id}) >\n{res3.response}")

    print("\n[STEP 4] Outgoing Operator Submits Handover for Review:")
    req4 = AgentRequest(
        user_id="op_john_console",
        user_role="CONSOLE_OPERATOR",
        session_id=session_id,
        message=f"Submit handover for Unit CDU-101"
    )
    res4 = orchestrator.execute(req4)
    print(f"User > {req4.message}")
    print(f"Agent ({res4.agent_id}) >\n{res4.response}")

    # -------------------------------------------------------------
    # Scenario 2: Role Authorization Enforcement
    # -------------------------------------------------------------
    print("\n[STEP 5] Field Operator tries to approve (Testing Role Security Interlock):")
    req5 = AgentRequest(
        user_id="op_mark_field",
        user_role="FIELD_OPERATOR",
        session_id=session_id,
        message=f"Approve handover for Unit CDU-101"
    )
    res5 = orchestrator.execute(req5)
    print(f"User > {req5.message}")
    print(f"Agent ({res5.agent_id}) >\n{res5.response}")

    # -------------------------------------------------------------
    # Scenario 3: Shift Supervisor Approves Handover
    # -------------------------------------------------------------
    print("\n[STEP 6] Shift Supervisor (Salem) approves the turnover package:")
    req6 = AgentRequest(
        user_id="sup_salem",
        user_role="SHIFT_SUPERVISOR",
        session_id=session_id,
        message=f"Approve handover for Unit CDU-101"
    )
    res6 = orchestrator.execute(req6)
    print(f"User > {req6.message}")
    print(f"Agent ({res6.agent_id}) >\n{res6.response}")

    # -------------------------------------------------------------
    # Scenario 4: Incoming Operator Acknowledges Safety Items & Accepts Custody
    # -------------------------------------------------------------
    print("\n[STEP 7] Incoming Operator (Alex) reviews safety items:")
    req7 = AgentRequest(
        user_id="op_alex_incoming",
        user_role="INCOMING_OPERATOR",
        session_id=session_id,
        message=f"Show active LOTO and safety items for Unit CDU-101"
    )
    res7 = orchestrator.execute(req7)
    print(f"User > {req7.message}")
    print(f"Agent ({res7.agent_id}) >\n{res7.response}")

    print("\n[STEP 8] Incoming Operator acknowledges LOTO item:")
    req8 = AgentRequest(
        user_id="op_alex_incoming",
        user_role="INCOMING_OPERATOR",
        session_id=session_id,
        message=f"Acknowledge safety items on Unit CDU-101"
    )
    res8 = orchestrator.execute(req8)
    print(f"User > {req8.message}")
    print(f"Agent ({res8.agent_id}) >\n{res8.response}")

    print("\n[STEP 9] Incoming Operator accepts custody (Transitions to COMPLETED):")
    req9 = AgentRequest(
        user_id="op_alex_incoming",
        user_role="INCOMING_OPERATOR",
        session_id=session_id,
        message=f"Acknowledge and accept handover for Unit CDU-101"
    )
    res9 = orchestrator.execute(req9)
    print(f"User > {req9.message}")
    print(f"Agent ({res9.agent_id}) >\n{res9.response}")

    # -------------------------------------------------------------
    # Scenario 5: Safety Interlock Equipment Command Refusal
    # -------------------------------------------------------------
    print("\n[STEP 10] Operator asks AI to perform autonomous plant command (Safety Guardrail):")
    req10 = AgentRequest(
        user_id="op_john_console",
        user_role="CONSOLE_OPERATOR",
        session_id=session_id,
        message="Shut down pump P-101 immediately"
    )
    res10 = orchestrator.execute(req10)
    print(f"User > {req10.message}")
    print(f"Agent ({res10.agent_id}) >\n{res10.response}")

    # -------------------------------------------------------------
    # Scenario 6: Audit History Inspection
    # -------------------------------------------------------------
    print("\n[STEP 11] Inspector queries the immutable audit history:")
    req11 = AgentRequest(
        user_id="auditor_sarah",
        user_role="HSE_REPRESENTATIVE",
        session_id=session_id,
        message=f"Show audit history for Unit CDU-101"
    )
    res11 = orchestrator.execute(req11)
    print(f"User > {req11.message}")
    print(f"Agent ({res11.agent_id}) >\n{res11.response}")

    print_separator("Demonstration Completed Successfully")

if __name__ == "__main__":
    main()
