import {
    isToday,
    isYesterday,
    isThisWeek,
    isThisMonth,
    parseISO,
  } from 'date-fns';
  
  export const groupSessionsByDate = (sessions) => {
    if (!sessions || sessions.length === 0) {
      return [];
    }
  
    const groups = {
      Today: [],
      Yesterday: [],
      'Previous 7 Days': [],
      'This Month': [],
      Older: [],
    };
  
    sessions.forEach((session) => {
      const sessionDate = parseISO(session.created_at);
  
      if (isToday(sessionDate)) {
        groups.Today.push(session);
      } else if (isYesterday(sessionDate)) {
        groups.Yesterday.push(session);
      } else if (isThisWeek(sessionDate, { weekStartsOn: 1 /* Monday */ })) {
        groups['Previous 7 Days'].push(session);
      } else if (isThisMonth(sessionDate)) {
          groups['This Month'].push(session);
      }
      else {
        groups.Older.push(session);
      }
    });
  
    return Object.entries(groups)
      .map(([title, sessions]) => ({ title, sessions }))
      .filter((group) => group.sessions.length > 0);
  };