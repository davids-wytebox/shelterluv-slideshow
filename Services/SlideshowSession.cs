using System.Windows.Threading;
using ShelterPetViewer.Models;

namespace ShelterPetViewer.Services;

public sealed class SlideshowSession : IDisposable
{
    private readonly List<CachedAnimal> _animals;
    private readonly int _historySize;
    private readonly Random _random = new();
    private readonly List<int> _history = new();
    private readonly DispatcherTimer _autoTimer;
    private EventHandler? _timerTickHandler;
    private int _historyPosition = -1;
    private int _currentIndex = -1;
    private bool _disposed;

    public event Action<CachedAnimal?>? AnimalChanged;

    public SlideshowSession(IReadOnlyList<CachedAnimal> animals, int autoAdvanceSeconds, int historySize)
    {
        _animals = animals.ToList();
        _historySize = historySize;
        _autoTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(autoAdvanceSeconds) };
        _timerTickHandler = (_, _) => ShowRandomNext();
        _autoTimer.Tick += _timerTickHandler;
    }

    public void Start()
    {
        ShowRandomNext();
        _autoTimer.Start();
    }

    public void Stop() => _autoTimer.Stop();

    public void ReloadAnimals(IReadOnlyList<CachedAnimal> animals)
    {
        ObjectDisposedException.ThrowIf(_disposed, this);

        _animals.Clear();
        _animals.AddRange(animals);
        _history.Clear();
        _historyPosition = -1;
        _currentIndex = -1;
        ShowRandomNext();
        ResetAutoTimer();
    }

    public void ShowNext()
    {
        if (CanGoForward())
        {
            _historyPosition++;
            ShowAt(_history[_historyPosition]);
            return;
        }

        ShowRandomNext();
    }

    public void ShowRandomNext()
    {
        if (_animals.Count == 0)
        {
            AnimalChanged?.Invoke(null);
            return;
        }

        int index;
        if (_animals.Count == 1)
            index = 0;
        else
        {
            do
            {
                index = _random.Next(_animals.Count);
            } while (index == _currentIndex);
        }

        TruncateForwardHistory();
        AppendHistory(index);
        ShowAt(index);
    }

    public void ShowPrevious()
    {
        if (!CanGoBack())
            return;

        _historyPosition--;
        ShowAt(_history[_historyPosition]);
    }

    public void ResetAutoTimer()
    {
        _autoTimer.Stop();
        _autoTimer.Start();
    }

    public void SetAutoAdvanceSeconds(int seconds)
    {
        _autoTimer.Interval = TimeSpan.FromSeconds(seconds);
        ResetAutoTimer();
    }

    public void Dispose()
    {
        if (_disposed)
            return;

        _disposed = true;
        _autoTimer.Stop();
        if (_timerTickHandler is not null)
            _autoTimer.Tick -= _timerTickHandler;
        AnimalChanged = null;
    }

    private bool CanGoBack() => _historyPosition > 0;

    private bool CanGoForward() =>
        _historyPosition >= 0 && _historyPosition < _history.Count - 1;

    private void ShowAt(int index)
    {
        _currentIndex = index;
        AnimalChanged?.Invoke(_animals[index]);
    }

    private void TruncateForwardHistory()
    {
        if (_historyPosition < _history.Count - 1)
            _history.RemoveRange(_historyPosition + 1, _history.Count - _historyPosition - 1);
    }

    private void AppendHistory(int index)
    {
        if (_historyPosition >= 0 && _history.Count > 0 && _history[_historyPosition] == index)
            return;

        _history.Add(index);
        _historyPosition = _history.Count - 1;

        while (_history.Count > _historySize)
        {
            _history.RemoveAt(0);
            _historyPosition--;
        }
    }
}
