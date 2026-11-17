import sys, os as _os
if __name__ == '__main__':
    sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', '..', '..'))
    from utils.utilities import UtilityFunctions
else:
    from ..utilities import UtilityFunctions
utils = UtilityFunctions()


# Plain x/y buffers: a data source appends to them, LivePlot redraws from them on every frame.
class XY_Data:
    def __init__(self):
        self.x = []
        self.y = []


# Live-updating line plot for Jupyter (ipympl "widget" backend). Shows the last plotted_data_len
# points (0 = all), rescaling the axes every interval ms.
# Usage:
#   data = XY_Data()
#   plot = LivePlot(data, title='Temperature')
#   plot.show(); plot.start()
#   data.x.append(t); data.y.append(v)   # from a loop or thread, picked up on the next frame
#   plot.stop()
class LivePlot:
    def __init__(self, xy_data, title='Live Data', plotted_data_len=20, interval=200, blit=False, save_count=5):
        # Checked here (at construction) rather than at module-import time, so merely importing
        # this module neither requires matplotlib/ipympl nor switches the notebook's plotting
        # backend - only actually instantiating LivePlot does.
        utils.exit_if_module_missing('matplotlib')
        utils.exit_if_module_missing('ipympl')
        import matplotlib.pyplot as plt
        import matplotlib.animation as animation
        utils.ipython_run_magic_command('matplotlib', 'widget')   # same as %matplotlib widget
        self._plt = plt
        self.plotted_data_len = plotted_data_len

        with plt.ioff():
            self.fig, ax = plt.subplots(figsize=(3, 2))
        plot, = ax.plot(xy_data.x, xy_data.y)
        ax.set_title(title)
        self.fig.suptitle(None)

        def animate(i):
            x_plot_data = xy_data.x
            y_plot_data = xy_data.y
            if len(xy_data.x):
                if self.plotted_data_len > 0:
                    x_plot_data = xy_data.x[-self.plotted_data_len:]
                    y_plot_data = xy_data.y[-self.plotted_data_len:]
                ax.axes.set_xlim(min(x_plot_data), max(x_plot_data))
                ax.axes.set_ylim(min(y_plot_data), max(y_plot_data))
            plot.set_data(x_plot_data, y_plot_data)

        self.ani = animation.FuncAnimation(
            fig=self.fig, func=animate, interval=interval, blit=blit, save_count=save_count)
        self.ani.event_source.stop()   # created paused; call start()

    def start(self):
        self.ani.event_source.start()

    def stop(self):
        self.ani.event_source.stop()

    def show(self):
        self._plt.show()

    def set_plotted_data_len(self, plotted_data_len):
        self.plotted_data_len = plotted_data_len
