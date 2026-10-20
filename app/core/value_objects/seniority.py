from enum import Enum


class SeniorityLevel(str, Enum):
    INTERN    = "intern"
    JUNIOR    = "junior"
    MID       = "mid"
    SENIOR    = "senior"
    EXPERT    = "expert"
    LEAD      = "lead"
    PRINCIPAL = "principal"
    UNKNOWN   = "unknown"
