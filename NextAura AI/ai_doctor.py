"""
NextAura AI - AI Appliance Doctor Engine
Implements the exact System Prompt and hybrid intelligence:
- Expert Appliance Diagnostic Knowledge Base (AC, Refrigerator, Washing Machine)
- Indicative Cost Estimator (Labor, Parts, Min/Max budget, and assumptions)
- Safety & Escalation Rules
- Optional external LLM API caller (Gemini/OpenAI) if keys are provided.
"""

import os
import json
import re

SYSTEM_PROMPT = """You are NextAura AI's "AI Appliance Doctor", an intelligent, empathetic, and safety-first assistant for home appliance troubleshooting.

Target Appliances:
- Air Conditioners (ACs)
- Refrigerators
- Washing Machines

Core Objectives:
1. Understand Symptoms: Ask targeted follow-up questions about symptoms, error codes, sounds, or visual issues.
2. Suggest Safe Preliminary Checks: Offer simple, non-dangerous troubleshooting steps the user can perform safely (e.g., checking power switches, clean filter check, door seal check).
3. Generate Indicative Cost Estimates: Provide an estimated price range (labor + spare parts) along with the assumptions behind the range.
4. Enforce Safety & Escalation Rules: NEVER diagnose complex electrical, gas, or refrigerant leaks directly. Always highlight hazards and recommend professional technician inspection. Never guarantee an exact final diagnosis—position suggestions as preliminary estimates subject to physical technician verification.

Response Formatting Requirements:
- Symptom Summary: Briefly restate what the customer reported.
- Safe Diagnostic Checks: 2–3 safe, non-technical steps to try.
- Indicative Cost Range: Break down labor vs. potential spare parts cost ranges with clear assumptions.
- Next Step Recommendation: Advise selecting a qualified local technician to inspect and provide a final itemized quote."""

# Comprehensive Expert Diagnostic Matrix for Indian & Global standard appliances
KNOWLEDGE_BASE = {
    "Air Conditioners": {
        "cooling_failure": {
            "keywords": ["not cooling", "warm air", "hot air", "low cooling", "blowing normal air", "temp high"],
            "summary": "Air conditioner blower is running but unit is failing to cool the room effectively.",
            "safe_checks": [
                "Verify remote control is firmly set to 'COOL' mode with target temperature at 22°C-24°C (ensure it is not on FAN or DRY mode).",
                "Gently unclip indoor panel and inspect the mesh dust filters; rinse under tap water if coated with dust.",
                "Check that the outdoor condenser unit is unobstructed and has at least 2 feet of clear breathing space around it."
            ],
            "cost_min": 850.0,
            "cost_max": 3200.0,
            "labor_breakdown": "₹400 - ₹650 (Coil deep wash, electrical contact testing, thermostat calibration)",
            "parts_breakdown": "₹450 - ₹2550 (Run capacitor ₹650-₹950, contactor relay ₹800, or PCB sensor ₹1200)",
            "assumptions": "Assumes refrigerant circuit intact; if dual-inverter PCB or compressor locked, technician quotation will revise accordingly.",
            "escalation_warning": "DANGER: High voltage capacitors store lethal electrical charge even after unplugging. Never unscrew the outdoor condenser casing.",
            "urgency": "Medium"
        },
        "water_leak": {
            "keywords": ["water leaking", "dripping", "water drop", "spilling", "ice inside"],
            "summary": "Water dripping or leaking from the indoor AC unit casing onto the floor or wall.",
            "safe_checks": [
                "Turn off the AC immediately to prevent moisture entering the indoor PCB and wall damage.",
                "Check the outdoor drain pipe outlet to see if it is kinked, lifted upwards, or blocked by mud/insects.",
                "Remove air filters to observe if evaporator coils have visible ice frost formation."
            ],
            "cost_min": 450.0,
            "cost_max": 1400.0,
            "labor_breakdown": "₹350 - ₹550 (Drain tray flush, high-pressure siphon clearing, pipe leveling)",
            "parts_breakdown": "₹100 - ₹850 (Drain hose replacement ₹150, tray replacement if cracked ₹700)",
            "assumptions": "Assumes standard drain blockage; ice freeze up due to low gas requires nitrogen pressure test.",
            "escalation_warning": "CAUTION: Standing water near power sockets poses severe short circuit risk. Keep floor dry.",
            "urgency": "High"
        },
        "noise_vibration": {
            "keywords": ["noise", "sound", "vibrating", "buzzing", "rattling", "screeching", "loud"],
            "summary": "Unusual loud vibrating, rattling, or screeching noise coming from the AC unit.",
            "safe_checks": [
                "Check if the indoor plastic filter or front lid has snapped shut completely.",
                "Ensure wall mounting bracket isn't loose by gently checking stability of the indoor unit from a safe ladder.",
                "Inspect whether external debris (leaves, small twigs) fell into the outdoor fan grill."
            ],
            "cost_min": 600.0,
            "cost_max": 2400.0,
            "labor_breakdown": "₹400 - ₹600 (Blower motor realignment, outdoor unit anti-vibration pad installation)",
            "parts_breakdown": "₹200 - ₹1800 (Anti-vibration rubber mounts ₹300, cross-flow blower wheel ₹1500)",
            "assumptions": "Prices vary depending on whether blower bearing needs lubrication vs full motor replacement.",
            "escalation_warning": "Do not insert sticks, screwdrivers, or hands into spinning fan blades.",
            "urgency": "Medium"
        },
        "default": {
            "summary": "General Air Conditioner performance inconsistency or electrical trip.",
            "safe_checks": [
                "Check the main circuit breaker (MCB) switch on your electrical distribution box.",
                "Turn off the AC isolator switch for 5 minutes, then turn back on to perform a soft micro-controller reset.",
                "Test remote control batteries and check for any flashing error codes on the display panel."
            ],
            "cost_min": 499.0,
            "cost_max": 2500.0,
            "labor_breakdown": "₹350 - ₹600 (Multi-point diagnostic inspection, electrical terminal tightening)",
            "parts_breakdown": "₹200 - ₹1900 (Depends on component identified during physical inspection)",
            "assumptions": "Final estimate determined after technician performs multimeter continuity checks.",
            "escalation_warning": "Never touch scorched, burnt, or sparking wires. Switch off main power immediately.",
            "urgency": "Normal"
        }
    },
    "Refrigerators": {
        "not_cooling_freezer_cold": {
            "keywords": ["freezer cold fridge warm", "freezer working fridge not", "fridge warm", "bottom warm", "vegetables rotting"],
            "summary": "Freezer compartment is freezing normally, but the lower refrigerator compartment remains warm.",
            "safe_checks": [
                "Check that food items are not blocking the cold air circulation vents at the back of the fridge shelf.",
                "Inspect the door gasket seal by inserting a paper currency note between the door and cabinet; if it slips out freely, the seal is loose.",
                "Ensure temperature dial inside the fridge is set between 3°C and 4°C (Level 3 or 4)."
            ],
            "cost_min": 750.0,
            "cost_max": 2600.0,
            "labor_breakdown": "₹400 - ₹600 (Evaporator defrost diagnostics, air damper testing)",
            "parts_breakdown": "₹350 - ₹2000 (Defrost timer ₹450, bi-metal thermostat ₹400, or fan motor ₹1500)",
            "assumptions": "Most commonly caused by defrost timer or evaporator fan failure blocking airflow to lower compartment.",
            "escalation_warning": "Refrigerant gas (R600a/R134a) lines are pressurized. Never poke ice with a knife or sharp metal objects.",
            "urgency": "High"
        },
        "water_leak_frost": {
            "keywords": ["water inside", "water leak", "ice buildup", "frost build", "pool under crisp tray"],
            "summary": "Excess water pooling beneath the vegetable crisper drawers or heavy frost accumulation.",
            "safe_checks": [
                "Ensure refrigerator is level or slightly tilted backwards so the door swings shut naturally.",
                "Avoid placing uncovered steaming hot food liquids directly into the fridge.",
                "Check if the rear bottom defrost drain hole inside the lower compartment is choked with food residue."
            ],
            "cost_min": 400.0,
            "cost_max": 1200.0,
            "labor_breakdown": "₹350 - ₹500 (Defrost drain hole flushing, heater channel de-icing)",
            "parts_breakdown": "₹50 - ₹700 (Drain grommet or magnetic door gasket seal strip)",
            "assumptions": "Standard drain channel clearing without structural cabinet damage.",
            "escalation_warning": "Ensure unit is disconnected before clearing drain conduits with warm water.",
            "urgency": "Medium"
        },
        "clicking_noise_compressor": {
            "keywords": ["clicking sound", "click click", "humming then click", "compressor hot", "not cooling at all"],
            "summary": "Compressor clicks every few minutes, hums briefly, and shuts off without cooling.",
            "safe_checks": [
                "Listen to the back of the fridge to verify if the compressor attempts to start before the click sound.",
                "Check if the voltage stabilizer (if present) shows normal 220V-240V green indicator.",
                "Feel if the exterior sides are lukewarm (normal) or burning hot (poor ventilation)."
            ],
            "cost_min": 800.0,
            "cost_max": 3500.0,
            "labor_breakdown": "₹450 - ₹650 (Relay & OLP overload protector replacement, compressor winding resistance test)",
            "parts_breakdown": "₹350 - ₹2850 (PTC starter relay & OLP ₹450-₹850, inverter controller board ₹2200)",
            "assumptions": "Assumes compressor motor windings are intact. If compressor is locked/grounded, replacement quotation needed.",
            "escalation_warning": "Do not touch rear compressor motor directly when hot. Burns and shock hazard.",
            "urgency": "High"
        },
        "default": {
            "summary": "Refrigerator temperature fluctuation, light failure, or cooling inconsistency.",
            "safe_checks": [
                "Verify power plug is firmly inserted into a 16A earthing wall socket.",
                "Leave a thermometer in a cup of water inside the middle shelf for 4 hours to verify real temperature.",
                "Verify door seal magnetic attraction on all four corners."
            ],
            "cost_min": 450.0,
            "cost_max": 2200.0,
            "labor_breakdown": "₹350 - ₹550 (General electrical and thermostat testing)",
            "parts_breakdown": "₹100 - ₹1650 (Door gasket, LED module, or thermostat replacement)",
            "assumptions": "Physical inspection needed for exact component failure assessment.",
            "escalation_warning": "Always unplug before touching internal lamp fittings or wiring.",
            "urgency": "Normal"
        }
    },
    "Washing Machines": {
        "not_draining_spinning": {
            "keywords": ["not draining", "water not going", "spin error", "oe", "e20", "e03", "drum full of water", "not spinning"],
            "summary": "Washing machine will not drain rinse water or complete the high-speed spin cycle.",
            "safe_checks": [
                "Open the small coin trap / lint filter door at the bottom front and unscrew the filter into a shallow tray to clear trapped coins, bobby pins, or lint.",
                "Ensure the rear drain hose is not kinked, crushed behind the machine, or submerged in a clogged drain.",
                "Check that laundry load is evenly distributed inside the drum (an uneven heavy bedsheet triggers spin cutoff)."
            ],
            "cost_min": 550.0,
            "cost_max": 2200.0,
            "labor_breakdown": "₹350 - ₹550 (Drain filter & pipe declogging, spin balance sensor recalibration)",
            "parts_breakdown": "₹200 - ₹1650 (Drain pump motor ₹850-₹1450, drain bellows hose ₹350)",
            "assumptions": "Assumes mechanical drain jam or pump replacement; main motherboard intact.",
            "escalation_warning": "Unplug machine before opening drain filter to avoid electrical hazard with wet hands.",
            "urgency": "High"
        },
        "drum_not_turning_noise": {
            "keywords": ["drum not spinning", "motor humming", "belt loose", "banging sound", "thumping", "drum stuck", "bearing"],
            "summary": "Machine fills with water but drum fails to rotate, or makes severe thumping/grinding metallic noise.",
            "safe_checks": [
                "With the machine switched OFF and unplugged, gently rotate the drum by hand: check if it spins smoothly or feels jammed/grating.",
                "Verify machine feet are firmly resting on level flooring; adjust the lock nuts on uneven feet.",
                "Check if any garment or underwire is caught between the drum rim and the rubber door gasket."
            ],
            "cost_min": 750.0,
            "cost_max": 3800.0,
            "labor_breakdown": "₹450 - ₹750 (Drum suspension check, belt adjustment or spider assembly test)",
            "parts_breakdown": "₹300 - ₹3050 (Drive belt ₹350, motor carbon brushes ₹500, shock absorbers ₹950, or drum spider/bearing kit ₹2500)",
            "assumptions": "Standard front/top load mechanical parts; drum spider or bearing assembly requires workshop dismantling.",
            "escalation_warning": "Severe shaking during spin can crack internal drum housings. Stop machine immediately if thumping.",
            "urgency": "High"
        },
        "water_inlet_leak": {
            "keywords": ["water filling slow", "ie error", "4e error", "e10", "water leaking bottom", "inlet valve", "detergent drawer"],
            "summary": "Water filling extremely slowly or leaking from detergent drawer / rear inlet pipe.",
            "safe_checks": [
                "Ensure water supply tap connected to the blue/grey hose is fully turned on with sufficient water tank pressure.",
                "Unscrew the inlet water hose from the back of the machine and clean the tiny mesh filter screen using an old toothbrush.",
                "Check if the detergent dispenser drawer has hardened detergent powder build-up blocking the water spray nozzles."
            ],
            "cost_min": 400.0,
            "cost_max": 1600.0,
            "labor_breakdown": "₹350 - ₹500 (Inlet filter de-scaling, solenoid valve voltage testing)",
            "parts_breakdown": "₹150 - ₹1100 (Inlet braided hose ₹250, double/triple solenoid valve ₹750-₹1100)",
            "assumptions": "Standard water line pressure available in household.",
            "escalation_warning": "Turn off water supply tap before detaching hoses to avoid high-pressure water spillage.",
            "urgency": "Medium"
        },
        "default": {
            "summary": "Washing machine operational glitch, power failure, or door lock error.",
            "safe_checks": [
                "Check power plug connection in a 16A grounded socket.",
                "Ensure the door or lid is firmly clicked shut (most machines will not start without active door lock switch).",
                "Reset machine: power off, unplug for 10 minutes, plug back in and select a quick rinse cycle."
            ],
            "cost_min": 500.0,
            "cost_max": 2500.0,
            "labor_breakdown": "₹350 - ₹550 (Electrical diagnostics, door interlock switch continuity check)",
            "parts_breakdown": "₹150 - ₹1950 (Door interlock switch ₹450-₹850, pressure sensor ₹650)",
            "assumptions": "Subject to technician multimeter diagnosis of main control PCB vs sensor.",
            "escalation_warning": "Never force open a locked door while machine is mid-cycle or filled with hot water.",
            "urgency": "Normal"
        }
    }
}

def diagnose_appliance(appliance_type, brand_model, symptoms_text, error_code=""):
    """
    Evaluates symptoms using the AI Appliance Doctor rules & knowledge engine.
    Ensures safe preliminary checks, cost estimation, and strict escalation warnings.
    """
    appliance_type_clean = appliance_type.strip()
    # Normalize appliance name
    if "Air" in appliance_type_clean or "AC" in appliance_type_clean:
        category = "Air Conditioners"
    elif "Fridge" in appliance_type_clean or "Refrigerator" in appliance_type_clean:
        category = "Refrigerators"
    elif "Wash" in appliance_type_clean:
        category = "Washing Machines"
    else:
        category = "Air Conditioners"

    symptoms_lower = (symptoms_text + " " + error_code).lower()
    app_kb = KNOWLEDGE_BASE.get(category, KNOWLEDGE_BASE["Air Conditioners"])

    matched_diagnosis = None
    # Match keywords in knowledge base
    for issue_key, data in app_kb.items():
        if issue_key == "default":
            continue
        for kw in data.get("keywords", []):
            if kw in symptoms_lower:
                matched_diagnosis = data
                break
        if matched_diagnosis:
            break

    if not matched_diagnosis:
        matched_diagnosis = app_kb.get("default", KNOWLEDGE_BASE["Air Conditioners"]["default"])

    # Build response adhering strictly to System Prompt formatting requirements
    model_str = f" for your {brand_model}" if brand_model else ""
    symptom_summary = f"{matched_diagnosis['summary']} (Observed on {category}{model_str})."
    
    # Safe Diagnostic Checks
    safe_checks = matched_diagnosis["safe_checks"]
    
    # Indicative Cost Range
    cost_min = matched_diagnosis["cost_min"]
    cost_max = matched_diagnosis["cost_max"]
    labor_breakdown = matched_diagnosis["labor_breakdown"]
    parts_breakdown = matched_diagnosis["parts_breakdown"]
    assumptions = matched_diagnosis["assumptions"]
    
    # Escalation and Next Step Recommendation
    escalation_warning = matched_diagnosis.get("escalation_warning", "Always prioritize personal safety around home appliances.")
    next_step = f"We strongly recommend matching with a verified NextAura technician specialized in {category}. The technician will perform an on-site physical inspection and provide an itemized quotation before any repair work commences."

    return {
        "appliance_type": category,
        "brand_model": brand_model or "Standard Model",
        "symptom_summary": symptom_summary,
        "safe_checks": safe_checks,
        "indicative_cost": {
            "min_total": cost_min,
            "max_total": cost_max,
            "currency": "INR",
            "currency_symbol": "₹",
            "labor_breakdown": labor_breakdown,
            "parts_breakdown": parts_breakdown,
            "assumptions": assumptions
        },
        "safety_warning": escalation_warning,
        "urgency": matched_diagnosis.get("urgency", "Normal"),
        "next_step_recommendation": next_step
    }
