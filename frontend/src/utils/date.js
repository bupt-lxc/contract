function pad2(value) {
  return String(value).padStart(2, "0");
}

export function formatLocalDate(date = new Date()) {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

function daysInMonth(year, monthIndex) {
  return new Date(year, monthIndex + 1, 0).getDate();
}

export function addDeadlineShortcut(baseDate, shortcut) {
  const match = String(shortcut || "").match(/^(\d+)([ym])$/);
  if (!match) return null;

  const amount = Number(match[1]);
  const unit = match[2];
  const result = new Date(baseDate.getTime());
  const originalDay = result.getDate();

  if (unit === "y") {
    const targetYear = result.getFullYear() + amount;
    const targetMonth = result.getMonth();
    result.setFullYear(targetYear, targetMonth, Math.min(originalDay, daysInMonth(targetYear, targetMonth)));
    return result;
  }

  const targetMonthAbsolute = result.getMonth() + amount;
  const targetYear = result.getFullYear() + Math.floor(targetMonthAbsolute / 12);
  const targetMonth = ((targetMonthAbsolute % 12) + 12) % 12;
  result.setFullYear(targetYear, targetMonth, Math.min(originalDay, daysInMonth(targetYear, targetMonth)));
  return result;
}

export function getDeadlineRange(shortcut, baseDate = new Date()) {
  const end = addDeadlineShortcut(baseDate, shortcut);
  if (!end) return {};
  return {
    deadline_from: formatLocalDate(baseDate),
    deadline_to: formatLocalDate(end),
  };
}
