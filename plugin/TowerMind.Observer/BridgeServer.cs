using System;
using System.Collections.Concurrent;
using System.IO;
using System.Net;
using System.Text;
using System.Threading;
using LitJson;

namespace SixAI.TowerMindPlugin
{
    internal sealed class PendingCommand
    {
        internal string body;
        internal string result;
        internal int statusCode;
        internal readonly ManualResetEvent completed = new ManualResetEvent(false);
    }

    internal sealed class DecisionOverlay
    {
        public string model { get; set; }
        public string analysis_summary { get; set; }
        public string action_text { get; set; }
        public string view { get; set; }
        public string outcome { get; set; }
        public bool can_retry { get; set; }
    }

    internal sealed class BridgeServer
    {
        private readonly int _port;
        private readonly object _cacheLock = new object();
        private readonly ConcurrentQueue<PendingCommand> _commands =
            new ConcurrentQueue<PendingCommand>();
        private HttpListener _listener;
        private Thread _thread;
        private volatile bool _running;
        private string _state = JsonUtil.Error("starting", "waiting for TowerMind scene");
        private string _mechanics = "{}";
        private DecisionOverlay _decision = new DecisionOverlay();
        private string _transitionAction = "";

        internal BridgeServer(int port)
        {
            _port = port;
        }

        internal void Start()
        {
            _listener = new HttpListener();
            _listener.Prefixes.Add("http://127.0.0.1:" + _port + "/");
            _listener.Start();
            _running = true;
            _thread = new Thread(ListenLoop)
            {
                IsBackground = true,
                Name = "TowerMindObserverHttp"
            };
            _thread.Start();
        }

        internal void Stop()
        {
            _running = false;
            try
            {
                _listener.Close();
            }
            catch
            {
                // Shutdown is best-effort.
            }
        }

        internal void SetState(string value)
        {
            lock (_cacheLock)
            {
                _state = value;
            }
        }

        internal void SetMechanics(string value)
        {
            lock (_cacheLock)
            {
                _mechanics = value;
            }
        }

        internal DecisionOverlay GetDecision()
        {
            lock (_cacheLock)
            {
                return _decision;
            }
        }

        internal void SetTransitionAction(string action)
        {
            lock (_cacheLock)
            {
                _transitionAction = action ?? "";
            }
        }

        internal bool TryDequeueCommand(out PendingCommand pending)
        {
            return _commands.TryDequeue(out pending);
        }

        private void ListenLoop()
        {
            while (_running)
            {
                try
                {
                    var context = _listener.GetContext();
                    ThreadPool.QueueUserWorkItem(_ => Handle(context));
                }
                catch (HttpListenerException)
                {
                    if (_running)
                    {
                        RuntimeLog.Warning("Observer HTTP listener stopped unexpectedly");
                    }
                }
                catch (ObjectDisposedException)
                {
                    return;
                }
                catch (Exception exc)
                {
                    RuntimeLog.Warning("Observer HTTP error: " + exc.Message);
                }
            }
        }

        private void Handle(HttpListenerContext context)
        {
            try
            {
                var request = context.Request;
                var path = request.Url.AbsolutePath.TrimEnd('/');
                if (path.Length == 0)
                {
                    path = "/";
                }
                if (request.HttpMethod == "OPTIONS")
                {
                    Write(context, 204, "");
                    return;
                }
                if (request.HttpMethod == "GET" && path == "/health")
                {
                    Write(context, 200, "{\"ok\":true,\"plugin\":\"TowerMind.Observer\",\"version\":\"" + RuntimeConstants.Version + "\"}");
                    return;
                }
                if (request.HttpMethod == "GET" && path == "/transition-action")
                {
                    string action;
                    lock (_cacheLock)
                    {
                        action = _transitionAction;
                    }
                    Write(
                        context,
                        200,
                        "{\"ok\":true,\"action\":\"" + action + "\"}"
                    );
                    return;
                }
                if (request.HttpMethod == "GET" && path == "/decision")
                {
                    DecisionOverlay decision;
                    lock (_cacheLock)
                    {
                        decision = _decision;
                    }
                    Write(
                        context,
                        200,
                        JsonMapper.ToJson(decision ?? new DecisionOverlay())
                    );
                    return;
                }
                if (request.HttpMethod == "GET" && path == "/state")
                {
                    string state;
                    lock (_cacheLock)
                    {
                        state = _state;
                    }
                    Write(context, 200, state);
                    return;
                }
                if (request.HttpMethod == "GET" && path == "/mechanics")
                {
                    string mechanics;
                    lock (_cacheLock)
                    {
                        mechanics = _mechanics;
                    }
                    Write(context, 200, mechanics);
                    return;
                }
                if (request.HttpMethod == "GET" && path == "/events")
                {
                    long after = 0;
                    long.TryParse(request.QueryString["after"], out after);
                    Write(context, 200, TelemetryStore.EventsJson(after));
                    return;
                }
                if (request.HttpMethod == "POST" && path == "/decision")
                {
                    var body = ReadBody(request);
                    var decision = JsonMapper.ToObject<DecisionOverlay>(body);
                    lock (_cacheLock)
                    {
                        _decision = decision ?? new DecisionOverlay();
                        _transitionAction = "";
                    }
                    Write(context, 200, "{\"ok\":true}");
                    return;
                }
                if (request.HttpMethod == "POST" && path == "/command")
                {
                    var pending = new PendingCommand { body = ReadBody(request) };
                    _commands.Enqueue(pending);
                    if (!pending.completed.WaitOne(5000))
                    {
                        Write(context, 504, JsonUtil.Error("command_timeout", "Unity main thread did not process the command in time"));
                        return;
                    }
                    Write(context, pending.statusCode, pending.result);
                    return;
                }
                Write(context, 404, JsonUtil.Error("not_found", path));
            }
            catch (Exception exc)
            {
                try
                {
                    Write(context, 500, JsonUtil.Error("server_error", exc.Message));
                }
                catch
                {
                    // Client disconnected.
                }
            }
        }

        private static string ReadBody(HttpListenerRequest request)
        {
            // Mono's macOS HttpListener can report ASCII here even when the
            // client explicitly sends charset=utf-8, replacing Chinese text
            // with question marks before JSON deserialization.
            using (var reader = new StreamReader(request.InputStream, Encoding.UTF8))
            {
                return reader.ReadToEnd();
            }
        }

        private static void Write(HttpListenerContext context, int status, string body)
        {
            var bytes = Encoding.UTF8.GetBytes(body ?? "");
            context.Response.StatusCode = status;
            context.Response.ContentType = "application/json; charset=utf-8";
            context.Response.ContentEncoding = Encoding.UTF8;
            context.Response.ContentLength64 = bytes.Length;
            context.Response.Headers["Access-Control-Allow-Origin"] = "http://127.0.0.1";
            context.Response.Headers["Access-Control-Allow-Headers"] = "Content-Type";
            context.Response.Headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS";
            if (bytes.Length > 0)
            {
                context.Response.OutputStream.Write(bytes, 0, bytes.Length);
            }
            context.Response.OutputStream.Close();
        }
    }

    internal static class JsonUtil
    {
        internal static string Error(string code, string message)
        {
            return JsonMapper.ToJson(
                new ErrorPayload
                {
                    ok = false,
                    error = code,
                    message = message ?? ""
                }
            );
        }

        private sealed class ErrorPayload
        {
            public bool ok { get; set; }
            public string error { get; set; }
            public string message { get; set; }
        }
    }
}
