// The one list of numbers for the whole web app. It matches HELPLINES in ml/iris_ml/support.py (the reviewed list the server sends with chat replies).
/** Lines to talk to someone now. */
export const HELPLINES = [
  { name: 'Tele-MANAS', detail: '24x7, free, confidential', number: '14416', tel: '14416' },
  { name: 'KIRAN', detail: 'Mental health helpline', number: '1800-599-0019', tel: '18005990019' },
] as const

/** Emergency services: police, ambulance and fire, anywhere in India. */
export const EMERGENCY = { name: 'In immediate danger', detail: 'Emergency services', number: '112', tel: '112' } as const

/** Every number, in the order the reviewed list uses. */
export const ALL_HELPLINES = [...HELPLINES, EMERGENCY]
