/** Русское согласование с числом: plural(1, ["замечание", "замечания", "замечаний"]) → "замечание". */
export function plural(n: number, forms: [string, string, string]): string {
  const abs = Math.abs(n);
  if (abs % 10 === 1 && abs % 100 !== 11) return forms[0];
  if (abs % 10 >= 2 && abs % 10 <= 4 && (abs % 100 < 10 || abs % 100 >= 20)) return forms[1];
  return forms[2];
}
