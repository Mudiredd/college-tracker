# scraper.py

from typing import List, Dict

# -----------------------------
# 1. SEMESTER → EXAM PERIOD MAP
# -----------------------------
SEM_TO_EXAMS = {
    1: [1, 2],
    2: [1, 2, 3],
    3: [1, 2, 3, 4],
    4: [1, 2, 3, 4, 5],
    5: [1, 2, 3, 4, 5, 6],
    6: [1, 2, 3, 4, 5, 6, 7],
    7: [1, 2, 3, 4, 5, 6, 7, 8],
    8: [1, 2, 3, 4, 5, 6, 7, 8],
}

# -----------------------------
# 2. ARREAR RULES (ODD / EVEN)
# -----------------------------
def get_allowed_exams_for_arrear(sem: int) -> List[int]:
    """
    Returns allowed exam periods based on semester arrear rules.
    """
    if sem == 1 or sem == 3:
        return [3, 5, 7]   # odd exams
    elif sem == 2 or sem == 4:
        return [4, 6, 8]   # even exams
    else:
        # default fallback
        return [1, 2, 3, 4, 5, 6, 7, 8]


# -----------------------------
# 3. MAIN LOGIC
# -----------------------------
def get_next_exam_periods(sem: int) -> List[int]:
    """
    Returns valid exam periods based on semester.
    """
    return SEM_TO_EXAMS.get(sem, [])


def filter_arrears(sem: int, arrears: List[str]) -> Dict:
    """
    Example input:
        sem = 3
        arrears = ["Math", "Physics"]

    Output:
        {
            "sem": 3,
            "allowed_exams": [5, 7],
            "subjects": [...]
        }
    """

    allowed_exams = get_allowed_exams_for_arrear(sem)

    return {
        "semester": sem,
        "allowed_exams": allowed_exams,
        "arrears": arrears,
        "message": f"Semester {sem} arrears can be cleared in exams {allowed_exams}"
    }


def get_exam_plan(sem: int) -> Dict:
    """
    Full semester exam planning.
    """

    return {
        "semester": sem,
        "next_exam_periods": get_next_exam_periods(sem),
        "arrear_rules": get_allowed_exams_for_arrear(sem)
    }


# -----------------------------
# 4. TEST (optional local run)
# -----------------------------
if __name__ == "__main__":
    print(get_exam_plan(3))
    print(filter_arrears(3, ["Math", "DBMS"]))