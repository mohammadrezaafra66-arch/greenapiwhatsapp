import React from "react";
import DatePicker, { DateObject } from "react-multi-date-picker";
import persian from "react-date-object/calendars/persian";
import persian_fa from "react-date-object/locales/persian_fa";
import TimePicker from "react-multi-date-picker/plugins/time_picker";

// V15 Item 21 — Shamsi (Jalali) date + time picker.
// Displays a Persian calendar (Persian month names + Persian numerals) but stores the
// value as a LATIN "YYYY/MM/DD HH:mm" string, exactly what the backend from_shamsi parses.
export default function ShamsiDateTimePicker({ value, onChange, placeholder }) {
  const dateObj = value
    ? new DateObject({ date: value, format: "YYYY/MM/DD HH:mm", calendar: persian, locale: persian_fa })
    : null;

  const pad = (n) => String(n).padStart(2, "0");

  return (
    <DatePicker
      calendar={persian}
      locale={persian_fa}
      calendarPosition="bottom-right"
      format="YYYY/MM/DD HH:mm"
      value={dateObj}
      inputClass="input"
      placeholder={placeholder}
      plugins={[<TimePicker key="tp" position="bottom" hideSeconds />]}
      onChange={(d) => {
        if (!d) return onChange("");
        // d is in the Persian calendar → d.year/d.month.number/d.day are Latin ints.
        onChange(`${d.year}/${pad(d.month.number)}/${pad(d.day)} ${pad(d.hour)}:${pad(d.minute)}`);
      }}
    />
  );
}
