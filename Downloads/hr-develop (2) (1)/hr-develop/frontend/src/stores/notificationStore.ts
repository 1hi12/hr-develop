import { create } from 'zustand';

export interface Notification {
  id: string;
  candidateName: string;
  seniority: string | null;
  timestamp: Date;
  read: boolean;
}

const MAX = 15;

interface NotificationStore {
  notifications: Notification[];
  unreadCount: number;
  addNotification: (candidateName: string, seniority?: string | null) => void;
  markAllAsRead: () => void;
  clearAll: () => void;
}

export const useNotificationStore = create<NotificationStore>((set) => ({
  notifications: [],
  unreadCount: 0,

  addNotification: (candidateName, seniority = null) => {
    const notif: Notification = {
      id: `${Date.now()}-${Math.random()}`,
      candidateName,
      seniority,
      timestamp: new Date(),
      read: false,
    };
    set((state) => {
      const list = [notif, ...state.notifications];
      // Si on dépasse MAX, on retire les plus anciennes (fin du tableau)
      const trimmed = list.length > MAX ? list.slice(0, MAX) : list;
      return {
        notifications: trimmed,
        unreadCount: trimmed.filter((n) => !n.read).length,
      };
    });
  },

  markAllAsRead: () =>
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, read: true })),
      unreadCount: 0,
    })),

  clearAll: () => set({ notifications: [], unreadCount: 0 }),
}));
