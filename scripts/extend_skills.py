"""One-shot script to broaden ``data/skills_seed.json`` with cross-domain
generic engineering skills so Atlas Vector Search has plausible neighbours
for non-bridge prompts (aerospace, mechanical, electrical, software, ...).

Idempotent: re-running won't duplicate entries.
"""
from __future__ import annotations

import json
import pathlib

p = pathlib.Path(__file__).resolve().parent.parent / "data" / "skills_seed.json"
existing = json.loads(p.read_text())

NEW = [
    # Mechanical / aerospace
    ("mechanical-design",       "Mechanical Design",                "engineering", "Generalist mechanical engineering: machine elements, kinematics, tolerancing, mechanism synthesis.",                                  ["mechanical","machine-design","kinematics","tolerancing"], 9800, 71),
    ("aerodynamics-and-cfd",    "Aerodynamics and CFD",             "engineering", "External and internal aerodynamics, lift/drag, boundary layers, CFD with RANS / LES turbulence models.",                          ["aerodynamics","cfd","fluid-dynamics","aerospace"],         8400, 62),
    ("propulsion-systems",      "Propulsion Systems",               "engineering", "Jet, turboprop, rocket and electric propulsion fundamentals; thrust/weight, specific impulse, intake design.",                  ["propulsion","jet","turbofan","aerospace"],                 6700, 48),
    ("airframe-and-fuselage",   "Airframe and Fuselage Design",     "engineering", "Aircraft structural layout: wing box, fuselage frames, empennage, pressurisation and fatigue allowables.",                     ["airframe","fuselage","aerospace","wing"],                  4900, 41),
    ("flight-controls",         "Flight Controls and Avionics",     "engineering", "Stability and control, fly-by-wire, autopilot logic, sensor fusion, certification (DO-178C / DO-254).",                          ["avionics","flight-controls","fly-by-wire","aerospace"],   3700, 35),
    ("thermodynamics-and-heat", "Thermodynamics and Heat Transfer", "engineering", "Cycle analysis, conduction/convection/radiation, heat exchangers, insulation sizing for engineering systems.",                   ["thermodynamics","heat-transfer","mechanical"],            7200, 55),
    ("hvac-design",             "HVAC and Building Services",       "engineering", "Heating, ventilation and air-conditioning load calculations, ductwork, refrigeration cycles, indoor air quality.",                ["hvac","building-services","mechanical"],                  5300, 39),
    ("acoustics-and-noise",     "Acoustics and Noise Control",      "engineering", "Architectural and machinery acoustics, sound transmission class, vibration isolation, NVH for vehicles.",                       ["acoustics","noise","nvh","vibration"],                    3100, 27),
    ("vibration-and-dynamics",  "Vibration and Dynamics",           "engineering", "Modal analysis, resonance avoidance, base-excitation problems, rotating-machinery dynamics, dampers.",                            ["vibration","dynamics","modal","mechanical"],              4400, 36),

    # Electrical / electronic / control
    ("electrical-power-systems","Electrical Power Systems",         "engineering", "Generation, distribution, three-phase circuits, transformers, motor drives, short-circuit studies.",                              ["electrical","power","grid","motors"],                     8800, 64),
    ("electronics-and-pcb",     "Electronics and PCB Design",       "engineering", "Analog and digital circuit design, schematic capture, multilayer PCB layout, EMC and signal integrity.",                          ["electronics","pcb","analog","digital"],                   9600, 78),
    ("embedded-firmware",       "Embedded Firmware",                "software",    "Bare-metal and RTOS firmware in C/C++ for microcontrollers; peripherals, interrupts, low-power design.",                          ["firmware","embedded","c","rtos"],                         7400, 84),
    ("control-systems",         "Control Systems Engineering",      "engineering", "Classical and modern control: PID tuning, state-space, robust and adaptive control, observers, Kalman filters.",                ["control","pid","state-space","kalman"],                   6200, 52),
    ("robotics-and-motion",     "Robotics and Motion Planning",     "engineering", "Forward/inverse kinematics, trajectory planning, ROS2, SLAM, manipulator dynamics, mobile-base navigation.",                     ["robotics","ros","motion-planning","slam"],                5800, 95),
    ("signal-processing",       "Signal and Image Processing",      "engineering", "Discrete-time filtering, FFT, wavelets, classical and deep-learning approaches to images and time series.",                       ["dsp","signal-processing","fft","imaging"],                7100, 73),

    # Materials / chemical / process
    ("materials-engineering",   "Materials Engineering (general)",  "engineering", "Cross-domain materials selection: metals, polymers, composites, ceramics; mechanical, thermal and corrosion properties.",        ["materials","metals","polymers","composites"],             9100, 68),
    ("composite-materials",     "Composite Materials",              "engineering", "CFRP/GFRP layup design, hand calculations and FE for laminates, joining, repair and certification.",                              ["composites","cfrp","laminate","aerospace"],               4600, 42),
    ("chemical-process-design", "Chemical Process Design",          "engineering", "Mass and energy balances, unit operations, reactor sizing, P&ID development, basic process safety (HAZOP).",                    ["chemical","process","reactor","pid-diagram"],             4100, 31),
    ("manufacturing-and-cnc",   "Manufacturing and CNC",            "engineering", "DFM/DFA, machining, sheet-metal, injection moulding, additive manufacturing, GD&T, CMM inspection.",                              ["manufacturing","cnc","dfm","gdt"],                        6800, 47),
    ("welding-and-joining",     "Welding and Joining",              "engineering", "Arc, MIG, TIG, friction-stir, adhesive and bolted joints; weld procedures, NDT, AWS / ISO codes.",                              ["welding","joining","aws","mechanical"],                   3300, 24),

    # Software / data / cloud
    ("software-architecture",   "Software Architecture",            "software",    "System decomposition, microservices vs modular monoliths, event-driven design, ADRs, non-functional requirements.",            ["software","architecture","microservices","ddd"],          8200, 92),
    ("backend-and-apis",        "Backend and API Engineering",      "software",    "REST and GraphQL APIs, authentication, rate-limiting, observability, SQL and NoSQL data modelling.",                              ["backend","api","rest","graphql"],                         9400, 110),
    ("cloud-infrastructure",    "Cloud Infrastructure",             "software",    "AWS/GCP/Azure, IaC with Terraform, Kubernetes, networking, IAM, cost-optimised architectures.",                                  ["cloud","aws","kubernetes","terraform"],                   8600, 88),
    ("data-engineering",        "Data Engineering",                 "software",    "Batch and streaming pipelines, warehouses, lakehouses, partitioning, quality, dbt and Spark.",                                  ["data","etl","spark","warehouse"],                         7600, 81),
    ("ml-engineering",          "Machine Learning Engineering",     "software",    "Training, evaluation and deployment of ML/LLM systems; MLOps, vector databases, evaluation harnesses.",                            ["ml","llm","mlops","vector"],                              9200, 124),
    ("cybersecurity",           "Cybersecurity Engineering",        "software",    "Threat modelling, OWASP Top 10, secure SDLC, secrets management, incident response, penetration testing basics.",               ["security","threat-modelling","owasp","appsec"],           6900, 58),

    # Industrial / human factors / sustainability
    ("industrial-design",       "Industrial and Product Design",    "design",      "Form, ergonomics, user empathy, prototyping, design language and product-market fit considerations.",                            ["industrial-design","product","ergonomics"],               5400, 33),
    ("ux-and-interaction",      "UX and Interaction Design",        "design",      "User research, journey mapping, wireframing, prototyping, accessibility (WCAG), usability testing.",                              ["ux","interaction","wcag","accessibility"],                6200, 46),
    ("human-factors",           "Human Factors and Ergonomics",     "engineering", "Anthropometrics, cognitive load, situational awareness, control-display compatibility, safety-critical UI.",                     ["human-factors","ergonomics","safety"],                    2800, 19),
    ("sustainability",          "Sustainability and ESG",           "engineering", "Life-cycle assessment, embodied carbon, circular-economy design, ESG reporting frameworks, scope 1-3.",                          ["sustainability","esg","lca","carbon"],                    4700, 38),
    ("regulatory-compliance",   "Regulatory and Standards Compliance","engineering","Cross-industry standards mapping (CE, FCC, FDA, ISO, IEC, FAA/EASA) and conformity-assessment routes.",                          ["regulatory","compliance","standards","ce"],               3500, 22),

    # Project / systems
    ("systems-engineering",     "Systems Engineering",              "engineering", "Requirements engineering, V-model, interface management, MBSE, V&V, INCOSE handbook practices.",                                ["systems-engineering","incose","mbse","requirements"],     5100, 37),
    ("project-management",      "Engineering Project Management",   "management",  "Scoping, scheduling, earned value, risk management, vendor coordination, stakeholder communication.",                              ["pm","scheduling","earned-value","risk"],                  6400, 28),
    ("safety-and-reliability",  "Safety and Reliability Engineering","engineering","FMEA, FTA, MTBF, FRACAS, functional safety (ISO 26262, IEC 61508), reliability allocation.",                                       ["safety","reliability","fmea","iso26262"],                 3900, 31),
]

cur_ids = {s["skill_id"] for s in existing}
added = 0
for sid, name, cat, desc, tags, installs, stars in NEW:
    if sid in cur_ids:
        continue
    existing.append({
        "skill_id": sid,
        "name": name,
        "description": desc,
        "category": cat,
        "tags": tags,
        "weekly_installs": installs,
        "github_stars": stars,
        "repo_url": f"https://github.com/example/{sid}",
    })
    added += 1

p.write_text(json.dumps(existing, indent=2) + "\n")
print(f"added {added}, total now {len(existing)}")
