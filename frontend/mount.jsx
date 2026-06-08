/**
 * mount - render the Dashboard into #root. Loaded last in the bundle.
 */
(function () {
  const el = document.getElementById("root");
  const root = ReactDOM.createRoot(el);
  root.render(<Dashboard />);
})();
