from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from icalendar import Calendar, Event,  Alarm


def _create(
            summary: str,
            description: str,
            location: str,
            date: str,
            heure: str
    ) -> bytes:
    """
    Crée .ics calendar. Sauvegarde en mémoire.
    """
    cal = Calendar()
    cal.add("prodid", "-//Mon Application//FR")
    cal.add("version", "2.0")

    # Créer un événement et ajouter information
    event = Event()
    event.add("summary", summary)
    event.add("location", location)
    event.add("description", description)
    dtstart = datetime.strptime(f"{date} {heure}", "%d/%m/%Y %H:%M")
    tz = ZoneInfo("Europe/Paris")
    dtstart = dtstart.replace(tzinfo=tz)
    dtend = dtstart.replace(hour=23, minute=59, second=0)
    event.add("dtstart", dtstart)
    event.add("dtend", dtend)
    event.add("dtstamp", datetime.now(tz))

    # Ajout rappel Rappel
    for reminder_days in (1, 3, 7, 14):
        alarm = Alarm()
        alarm.add("action", "DISPLAY")
        alarm.add("description", f"Rappel : {summary}")
        alarm.add("trigger", timedelta(days=-reminder_days))
        event.add_component(alarm)

    # 3. Ajouter l'événement au calendrier
    cal.add_component(event)

    return cal.to_ical()