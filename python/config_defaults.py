LINE_OPS = ["BT01", "BT02", "BT03", "BT04", "BT05", "BT06", "BT07", "BT08", "BT09"]

EQUIPMENTS = [
    "Wave Soldering",
    "AOI Wave",
    "AOI Coating",
    "X-ray",
    "RTV",
    "Coating",
    "Robot Packing",
    "Conveyor",
    "Auto Insertion",
    "Router",
    "KED Cleaning Pallet",
    "KED Cleaning PCB",
    "DCT Cleaning PCB",
    "Etc..",
]

PROBLEM_MAP = {
    "Wave Soldering": [
        "Covert Program",
        "Clean Nozzle",
        "Flux Empty",
        "Fill Solder",
        "Machine Down",
        "Board Drop",
        "Fine-tune Program",
    ],
    "AOI Wave": ["Covert Program", "Machine Down", "Full Storage Data", "Board Drop", "Fine-tune Program"],
    "AOI Coating": ["Covert Program", "Machine Down", "Full Storage Data", "Board Drop", "Fine-tune Program"],
    "X-ray": ["Covert Program", "Machine Down", "Full Storage Data", "Board Drop", "Fine-tune Program"],
    "RTV": [
        "Covert Program",
        "Nozzle Broken",
        "Nozzle Clog",
        "Fill Glue",
        "Fill Coating Liquid",
        "Machine Down",
        "Board Drop",
        "Fine-tune Program",
    ],
    "Coating": [
        "Covert Program",
        "Nozzle Broken",
        "Nozzle Clog",
        "Fill Glue",
        "Fill Coating Liquid",
        "Machine Down",
        "Board Drop",
        "Fine-tune Program",
    ],
    "Robot Packing": [
        "Covert Program",
        "Machine Down",
        "Sensors Error",
        "Vacuum Error",
        "Camera Error",
        "Board Drop",
        "Robot not movement",
        "Robot Error",
    ],
    "Conveyor": ["Machine Down", "Board Can't Transfer", "Board Drop"],
    "Auto Insertion": ["Covert Program", "Machine Down", "Can't Placement Part", "Fine-tune Program"],
    "Router": [
        "Covert Program",
        "Machine Down",
        "Change Router Bit",
        "Router Bit Broken",
        "Dust Cabinet Not Working",
        "Fine-tune Program",
    ],
    "KED Cleaning Pallet": [
        "Covert Program",
        "Machine Down",
        "Fill Chemical",
        "Fine-tune Program",
        "System Chemical Leak",
        "Chemical Over Flow",
    ],
    "KED Cleaning PCB": [
        "Covert Program",
        "Machine Down",
        "Fill Chemical",
        "Fine-tune Program",
        "System Chemical Leak",
        "Chemical Over Flow",
    ],
    "DCT Cleaning PCB": [
        "Covert Program",
        "Machine Down",
        "Fill Chemical",
        "Fine-tune Program",
        "System Chemical Leak",
        "Chemical Over Flow",
    ],
}

EXTRA_LINE_OPS = ["PACKING", "REWORK", "CLEANING"]

MACHINE_TYPE_MAP_DEFAULT = {
    "Wave Soldering": ["ECO1 SELECT", "ERSA VERSAFLOW"],
    "AOI Wave": ["Jet", "Nordson", "Axxon", "Yamaha"],
    "AOI Coating": ["Jet", "Nordson", "Axxon", "Yamaha"],
    "X-ray": ["Vitrox", "Omron"],
    "RTV": ["Mycronic", "Nordson"],
    "Coating": ["Mycronic", "Nordson"],
    "UV Curing": ["Nutek", "Nordson"],
    "Robotic": ["Robot KUKA"],
    "Auto Insertion": ["FACC"],
    "Router": ["Aurotek Router", "Cencorp Router"],
    "Cleaning Machine": ["DCT Twin", "KED D1000", "KED AT5000"],
    "Rework Machine": ["SRT Machine", "Minipot", "Oven"],
    "Etc..": ["Other M/C or Tools"],
}

DEFAULT_SUPPORT_AREAS = ["Backline", "Inspection", "Coating & Robotic", "Rework", "Etc.."]
DEFAULT_SUPPORT_AREA_MAP = {
    "Backline": ["Wave Soldering", "Auto Insertion", "Router", "Cleaning Machine"],
    "Inspection": ["AOI Wave", "AOI Coating", "X-ray"],
    "Coating & Robotic": ["RTV", "Coating", "UV Curing", "Robotic"],
    "Rework": ["Rework Machine"],
    "Etc..": ["Etc.."],
}
LINE_MACHINE_MAP_SETTING_KEY = "line_machine_map_v1"
LEGACY_LINE_MACHINE_MAP_FILE = "database/monitoring_line_map.json"
LINE_MACHINE_MAP_FILE_ENV = "SUPPORTHUB_LINE_MACHINE_MAP_FILE"
LINE_MACHINE_ITEM_SEPARATOR = "|||"

MASTER_STATUS_TEXT = {
    "line_added": "Added new Line No. successfully",
    "line_exists": "Line No. already exists",
    "line_deleted": "Deleted Line No. successfully",
    "line_not_found": "Line No. not found",
    "machine_added": "Added new Machine successfully",
    "machine_exists": "Machine already exists",
    "machine_deleted": "Deleted Machine successfully",
    "machine_not_found": "Machine not found",
    "machine_type_added": "Added new Machine Type successfully",
    "machine_type_exists": "Machine Type already exists for this Machine",
    "machine_type_deleted": "Deleted Machine Type successfully",
    "machine_type_not_found": "Machine Type not found",
    "machine_id_added": "Added new Machine ID successfully",
    "machine_id_exists": "Machine ID already exists for this Machine Type",
    "machine_id_deleted": "Deleted Machine ID successfully",
    "machine_id_not_found": "Machine ID not found",
    "support_area_added": "Added new Support Area successfully",
    "support_area_exists": "Support Area already exists",
    "support_area_deleted": "Deleted Support Area successfully",
    "support_area_not_found": "Support Area not found",
    "support_area_map_added": "Mapped Support Area to Machine successfully",
    "support_area_map_exists": "This Support Area and Machine mapping already exists",
    "support_area_map_deleted": "Deleted Support Area and Machine mapping successfully",
    "support_area_map_not_found": "Support Area and Machine mapping not found",
    "problem_added": "Added new Problem successfully",
    "problem_exists": "Problem already exists",
    "problem_deleted": "Deleted Problem successfully",
    "problem_not_found": "Problem not found",
    "line_machine_map_added": "Mapped Line No. to Monitoring item successfully",
    "line_machine_map_exists": "This Line No. and Monitoring item mapping already exists",
    "line_machine_map_deleted": "Deleted Line No. and Monitoring item mapping successfully",
    "line_machine_map_not_found": "Line No. and Monitoring item mapping not found",
    "invalid_input": "Please provide all required fields",
}

MASTER_SEED_KEY = "master_seed_v1"

