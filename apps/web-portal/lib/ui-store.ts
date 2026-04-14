import { create } from 'zustand';

type Speed = 1 | 2 | 5;

type DashboardWidget = 'health' | 'ticker' | 'risk' | 'network' | 'latency' | 'users';

type UiStore = {
  feedPaused: boolean;
  feedSpeed: Speed;
  dashboardWidgets: DashboardWidget[];
  setFeedPaused: (value: boolean) => void;
  setFeedSpeed: (value: Speed) => void;
  moveWidget: (from: number, to: number) => void;
  resetWidgets: () => void;
};

const DEFAULT_WIDGETS: DashboardWidget[] = ['health', 'ticker', 'risk', 'network', 'latency', 'users'];

export const useUiStore = create<UiStore>((set) => ({
  feedPaused: false,
  feedSpeed: 1,
  dashboardWidgets: DEFAULT_WIDGETS,
  setFeedPaused: (value) => set({ feedPaused: value }),
  setFeedSpeed: (value) => set({ feedSpeed: value }),
  moveWidget: (from, to) => set((state) => {
    const widgets = [...state.dashboardWidgets];
    const [item] = widgets.splice(from, 1);
    widgets.splice(to, 0, item);
    return { dashboardWidgets: widgets };
  }),
  resetWidgets: () => set({ dashboardWidgets: DEFAULT_WIDGETS }),
}));
