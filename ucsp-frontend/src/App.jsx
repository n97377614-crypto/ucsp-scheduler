import { useState, useEffect, useCallback, useRef } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, AreaChart, Area,
} from "recharts";
import {
  LayoutDashboard, Cpu, Clock, Grid3x3, BarChart2,
  Download, RefreshCw, CheckCircle, AlertCircle, Loader2,
  Database, Users, BookOpen, Building2, Play, ChevronRight,
  ArrowUpDown, Settings2, Layers, Zap, FileDown, Copy,
  GraduationCap, CalendarDays, Trophy, X,
} from "lucide-react";

const API = "http://localhost:8000";

/* ─── palette ─── */
const C = {
  bg: "#080a0f",
  s1: "#0f1118",
  s2: "#161924",
  s3: "#1d2130",
  border: "#252838",
  gold: "#e8b84b",
  goldDim: "#9c7b32",
  text: "#e2e4ee",
  muted: "#6b6e82",
  green: "#4ade80",
  red: "#f87171",
  blue: "#60a5fa",
  purple: "#a78bfa",
};

const COURSE_PALETTE = [
  "#e8b84b","#60a5fa","#4ade80","#f87171","#a78bfa",
  "#fb923c","#34d399","#f472b6","#38bdf8","#c084fc",
];

/* ─── mock data ─── */
const MOCK_INSTANCE = {
  name: "galala_demo", num_teachers: 12, num_classrooms: 8,
  num_courses: 18, num_admin_classes: 6, num_events: 24,
  joint_events: 6, indep_events: 18,
  teachers: [
    {id:1,name:"Dr. Ahmed Hassan",dept:"CS"},{id:2,name:"Dr. Sara Mahmoud",dept:"Math"},
    {id:3,name:"Dr. Youssef Ali",dept:"CS"},{id:4,name:"Prof. Nadia Ibrahim",dept:"EE"},
  ],
  classrooms: [
    {id:1,name:"LH-101",capacity:80,type:"lecture"},{id:2,name:"LH-102",capacity:60,type:"lecture"},
    {id:3,name:"LAB-A",capacity:40,type:"lab"},{id:4,name:"LAB-B",capacity:35,type:"lab"},
  ],
  admin_classes: [
    {id:1,name:"CS-Y1",students:45},{id:2,name:"CS-Y2",students:42},
    {id:3,name:"CS-Y3",students:38},{id:4,name:"Math-Y1",students:50},
  ],
};

const MOCK_TIMETABLE = {
  admin_class: "CS-Y2",
  events_count: 8,
  grid: [
    { period:"P1", days:{ Mon:{course:"CS301",teacher:"Dr. Ahmed Hassan",room:"LH-101",joint:false}, Tue:{course:"MATH201",teacher:"Dr. Sara Mahmoud",room:"LH-102",joint:false}, Wed:{}, Thu:{course:"CS310",teacher:"Dr. Youssef Ali",room:"LH-101",joint:true}, Fri:{} }},
    { period:"P2", days:{ Mon:{}, Tue:{course:"CS301",teacher:"Dr. Ahmed Hassan",room:"LH-101",joint:false}, Wed:{course:"EE201",teacher:"Prof. Nadia Ibrahim",room:"LH-102",joint:false}, Thu:{}, Fri:{course:"MATH201",teacher:"Dr. Sara Mahmoud",room:"LH-102",joint:false} }},
    { period:"P3", days:{ Mon:{course:"CS205",teacher:"Dr. Youssef Ali",room:"LAB-A",joint:false}, Tue:{}, Wed:{course:"CS301",teacher:"Dr. Ahmed Hassan",room:"LH-101",joint:false}, Thu:{course:"CS205",teacher:"Dr. Youssef Ali",room:"LAB-A",joint:false}, Fri:{} }},
    { period:"P4", days:{ Mon:{}, Tue:{course:"CS310",teacher:"Dr. Youssef Ali",room:"LH-101",joint:true}, Wed:{}, Thu:{}, Fri:{course:"EE201",teacher:"Prof. Nadia Ibrahim",room:"LH-102",joint:false} }},
    { period:"P5", days:{ Mon:{}, Tue:{}, Wed:{}, Thu:{course:"MATH201",teacher:"Dr. Sara Mahmoud",room:"LH-102",joint:false}, Fri:{} }},
  ],
};

function genFitnessHistory(gens=120) {
  const h = [], a = [];
  let b = 2_000_000 + Math.random()*500_000;
  let avg = b * 1.4;
  for(let i=0;i<gens;i++){
    b = Math.max(0, b * (0.985 + Math.random()*0.01 - 0.005));
    avg = Math.max(b, avg * (0.99 + Math.random()*0.008));
    h.push(parseFloat(b.toFixed(1)));
    a.push(parseFloat(avg.toFixed(1)));
  }
  return {best:h, avg:a};
}

const MOCK_HIST = genFitnessHistory(120);
const MOCK_RESULT = {
  feasible: true, final_fitness: 67.5, hard_violations: 0,
  classrooms_used: 6, occupancy_pct: 73.4,
  fitness_breakdown: {
    feasible: true, fitness: 67.5, hard_total: 0,
    hard_penalty: 0, soft_penalty: 67.5,
    soft_detail: { sc1: 8.5, sc2: 12.0, sc3: 11.0, sc4: 30.0, sc5: 6.0, total: 67.5 },
    hard_detail: { hc1_teacher_conflict:0,hc3_class_conflict:0,hc4_required_hours:0,hc6_joint_coord:0,hc8_fixed_slots:0 },
  },
  phase1_fitness_history: MOCK_HIST.best.slice(0,60),
  phase2_fitness_history: MOCK_HIST.best.slice(60),
};

/* ─── helpers ─── */
function apiCall(path, opts={}) {
  return fetch(API + path, { headers:{"Content-Type":"application/json"}, ...opts })
    .then(r => { if(!r.ok) throw new Error(`${r.status}`); return r.json(); });
}

function Tag({ children, color="#e8b84b" }) {
  return (
    <span style={{
      background: color+"22", color, border:`1px solid ${color}44`,
      borderRadius:4, padding:"1px 8px", fontSize:11, fontFamily:"monospace", fontWeight:600,
    }}>{children}</span>
  );
}

function StatCard({ icon: Icon, label, value, sub, accent=C.gold }) {
  return (
    <div style={{
      background:C.s2, border:`1px solid ${C.border}`,
      borderRadius:12, padding:"20px 22px", display:"flex", flexDirection:"column", gap:8,
    }}>
      <div style={{display:"flex",alignItems:"center",gap:8,color:C.muted,fontSize:12,letterSpacing:"0.08em",textTransform:"uppercase"}}>
        <Icon size={14} style={{color:accent}}/>{label}
      </div>
      <div style={{fontSize:28,fontWeight:700,color:C.text,fontFamily:"'Cormorant Garamond',serif",lineHeight:1}}>{value}</div>
      {sub && <div style={{fontSize:12,color:C.muted}}>{sub}</div>}
    </div>
  );
}

function StatusBadge({ status }) {
  const map = {
    PENDING:   [C.gold,"pending"],
    RUNNING:   [C.blue,"running"],
    COMPLETED: [C.green,"completed"],
    FAILED:    [C.red,"failed"],
    CANCELLED: [C.muted,"cancelled"],
  };
  const [color, label] = map[status] || [C.muted, status];
  return <Tag color={color}>{label}</Tag>;
}

/* ─── main app ─── */
export default function App() {
  const [view, setView]       = useState("dashboard");
  const [demoMode, setDemo]   = useState(true);
  const [instance, setInstance] = useState(null);
  const [jobs, setJobs]       = useState([]);
  const [activeJob, setActiveJob] = useState(null);
  const [result, setResult]   = useState(null);
  const [timetable, setTimetable] = useState(null);
  const [selectedClass, setSelectedClass] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [polling, setPolling] = useState(false);
  const [toast, setToast]     = useState(null);
  const [genConfig, setGenConfig] = useState({
    population_size: 50, max_generations: 200,
    crossover_prob: 0.8, mutation_prob: 0.01,
    tournament_k: 3, time_limit_sec: 300,
  });

  const pollRef = useRef(null);

  const showToast = useCallback((msg, type="info") => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3500);
  }, []);

  /* load instance */
  useEffect(() => {
    if(demoMode) { setInstance(MOCK_INSTANCE); return; }
    apiCall("/instances/galala_demo").then(setInstance).catch(() => {
      setDemo(true); setInstance(MOCK_INSTANCE);
      showToast("Backend unreachable — switched to Demo Mode", "warn");
    });
  }, [demoMode]);

  /* poll active job */
  useEffect(() => {
    if(!activeJob || polling) return;
    if(demoMode) {
      setPolling(true);
      let g = 0;
      const iv = setInterval(() => {
        g += 10;
        if(g >= 100) {
          clearInterval(iv);
          setResult(MOCK_RESULT);
          setPolling(false);
          setGenerating(false);
          showToast("Schedule generated successfully!", "success");
          setView("timetable");
          setTimetable(MOCK_TIMETABLE);
        }
        setJobs(prev => prev.map(j => j.job_id === activeJob
          ? {...j, progress: g, status: g>=100?"COMPLETED":"RUNNING"}
          : j));
      }, 300);
      return () => clearInterval(iv);
    }
    setPolling(true);
    pollRef.current = setInterval(() => {
      apiCall(`/schedules/jobs/${activeJob}`).then(data => {
        setJobs(prev => prev.map(j => j.job_id === activeJob ? {...j, ...data} : j));
        if(data.status === "COMPLETED") {
          clearInterval(pollRef.current); setPolling(false); setGenerating(false);
          setResult(data.result); showToast("Schedule generated!", "success");
          setView("timetable");
        } else if(data.status === "FAILED") {
          clearInterval(pollRef.current); setPolling(false); setGenerating(false);
          showToast("Generation failed: "+data.error, "error");
        }
      }).catch(() => { clearInterval(pollRef.current); setPolling(false); });
    }, 1200);
    return () => clearInterval(pollRef.current);
  }, [activeJob, demoMode]);

  /* start generation */
  const handleGenerate = useCallback(() => {
    if(generating) return;
    setGenerating(true);
    const jid = Math.random().toString(36).slice(2,10);
    const newJob = { job_id:jid, status:"PENDING", progress:0, instance:"galala_demo" };
    setJobs(prev => [newJob, ...prev]);
    setActiveJob(jid);
    setView("jobs");
    if(demoMode) return;
    apiCall("/schedules/generate", {
      method:"POST",
      body: JSON.stringify({ instance_name:"galala_demo", ...genConfig }),
    }).then(data => {
      setActiveJob(data.job_id);
      setJobs(prev => [{ job_id:data.job_id, status:"RUNNING", progress:0, instance:"galala_demo" }, ...prev.slice(1)]);
    }).catch(e => {
      setGenerating(false); showToast("Failed to start: "+e.message, "error");
    });
  }, [generating, demoMode, genConfig]);

  /* load timetable */
  const loadTimetable = useCallback((cls) => {
    setSelectedClass(cls);
    if(demoMode) { setTimetable(MOCK_TIMETABLE); return; }
    apiCall(`/schedules/${activeJob}/timetable?admin_class_name=${encodeURIComponent(cls)}`).then(setTimetable).catch(() => setTimetable(MOCK_TIMETABLE));
  }, [demoMode, activeJob]);

  const navItems = [
    { id:"dashboard", label:"Dashboard",    icon:LayoutDashboard },
    { id:"generate",  label:"Generate",     icon:Cpu },
    { id:"jobs",      label:"Jobs",         icon:Clock },
    { id:"timetable", label:"Timetable",    icon:Grid3x3 },
    { id:"analytics", label:"Analytics",   icon:BarChart2 },
    { id:"export",    label:"Export",       icon:FileDown },
  ];

  return (
    <div style={{ display:"flex", height:"100vh", background:C.bg, color:C.text, fontFamily:"'Outfit',sans-serif", overflow:"hidden" }}>
      <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600;700&family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet"/>

      {/* ── Sidebar ── */}
      <aside style={{
        width:220, background:C.s1, borderRight:`1px solid ${C.border}`,
        display:"flex", flexDirection:"column", flexShrink:0,
      }}>
        {/* Logo */}
        <div style={{ padding:"28px 20px 20px", borderBottom:`1px solid ${C.border}` }}>
          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
            <div style={{
              width:36, height:36, borderRadius:8,
              background:`linear-gradient(135deg,${C.gold},${C.goldDim})`,
              display:"flex", alignItems:"center", justifyContent:"center",
            }}>
              <GraduationCap size={20} color="#0a0b0f"/>
            </div>
            <div>
              <div style={{ fontSize:13, fontWeight:700, color:C.text, letterSpacing:"0.02em" }}>UCSP</div>
              <div style={{ fontSize:10, color:C.muted, letterSpacing:"0.06em", textTransform:"uppercase" }}>POGA-DP</div>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ flex:1, padding:"12px 10px", display:"flex", flexDirection:"column", gap:2 }}>
          {navItems.map(({ id, label, icon:Icon }) => {
            const active = view === id;
            return (
              <button key={id} onClick={() => setView(id)} style={{
                display:"flex", alignItems:"center", gap:10, padding:"9px 12px",
                borderRadius:8, border:"none", cursor:"pointer", textAlign:"left",
                background: active ? `${C.gold}18` : "transparent",
                color: active ? C.gold : C.muted,
                fontSize:13, fontWeight: active?600:400,
                transition:"all .15s",
              }}>
                <Icon size={16}/>{label}
                {id==="jobs" && jobs.some(j=>j.status==="RUNNING") && (
                  <span style={{ marginLeft:"auto", width:6, height:6, borderRadius:"50%", background:C.blue, boxShadow:`0 0 6px ${C.blue}` }}/>
                )}
              </button>
            );
          })}
        </nav>

        {/* Demo toggle */}
        <div style={{ padding:"12px 14px", borderTop:`1px solid ${C.border}` }}>
          <button onClick={() => setDemo(!demoMode)} style={{
            width:"100%", padding:"8px 12px", borderRadius:8,
            border:`1px solid ${demoMode ? C.goldDim : C.border}`,
            background: demoMode ? `${C.gold}12` : "transparent",
            color: demoMode ? C.gold : C.muted,
            fontSize:11, letterSpacing:"0.06em", textTransform:"uppercase",
            cursor:"pointer", fontWeight:600, display:"flex", alignItems:"center", gap:8,
          }}>
            <Zap size={12}/>{demoMode ? "Demo Mode" : "Live Mode"}
          </button>
        </div>
      </aside>

      {/* ── Main ── */}
      <main style={{ flex:1, display:"flex", flexDirection:"column", overflow:"hidden" }}>
        {/* Top bar */}
        <header style={{
          height:56, borderBottom:`1px solid ${C.border}`,
          display:"flex", alignItems:"center", justifyContent:"space-between",
          padding:"0 28px", background:C.s1, flexShrink:0,
        }}>
          <div style={{ display:"flex", alignItems:"center", gap:8, fontSize:13, color:C.muted }}>
            <span style={{ color:C.text, fontWeight:500 }}>Galala University</span>
            <ChevronRight size={14}/>
            <span style={{ color:C.gold }}>{navItems.find(n=>n.id===view)?.label}</span>
          </div>
          <div style={{ display:"flex", alignItems:"center", gap:12 }}>
            {instance && <Tag color={C.green}>{instance.num_events} events</Tag>}
            {demoMode && <Tag color={C.purple}>demo</Tag>}
          </div>
        </header>

        {/* Content */}
        <div style={{ flex:1, overflow:"auto", padding:28 }}>
          {view==="dashboard" && <Dashboard instance={instance} result={result} onGenerate={() => setView("generate")}/>}
          {view==="generate"  && <Generate config={genConfig} setConfig={setGenConfig} onRun={handleGenerate} generating={generating} instance={instance}/>}
          {view==="jobs"      && <Jobs jobs={jobs} activeJob={activeJob} result={result}/>}
          {view==="timetable" && <Timetable timetable={timetable} instance={instance} onLoadClass={loadTimetable} result={result} selectedClass={selectedClass}/>}
          {view==="analytics" && <Analytics result={result} hist={MOCK_HIST}/>}
          {view==="export"    && <Export activeJob={activeJob} result={result} demoMode={demoMode}/>}
        </div>
      </main>

      {/* Toast */}
      {toast && (
        <div style={{
          position:"fixed", bottom:24, right:24, zIndex:999,
          background: toast.type==="success" ? `${C.green}22` : toast.type==="error" ? `${C.red}22` : `${C.gold}18`,
          border:`1px solid ${toast.type==="success"?C.green:toast.type==="error"?C.red:C.gold}44`,
          color: toast.type==="success"?C.green:toast.type==="error"?C.red:C.gold,
          borderRadius:10, padding:"12px 18px", fontSize:13, fontWeight:500,
          display:"flex", alignItems:"center", gap:10, maxWidth:340,
          animation:"slideUp .25s ease",
        }}>
          {toast.type==="success"?<CheckCircle size={15}/>:<AlertCircle size={15}/>}
          {toast.msg}
        </div>
      )}

      <style>{`
        @keyframes slideUp { from{opacity:0;transform:translateY(12px)} to{opacity:1;transform:translateY(0)} }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.5} }
        ::-webkit-scrollbar { width:5px; height:5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #2a2d3a; border-radius:10px; }
        * { box-sizing:border-box; }
        button:focus { outline:none; }
      `}</style>
    </div>
  );
}

/* ══ DASHBOARD ══ */
function Dashboard({ instance, result, onGenerate }) {
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:24 }}>
      <div>
        <h1 style={{ fontFamily:"'Cormorant Garamond',serif", fontSize:32, fontWeight:700, color:C.text, margin:0, lineHeight:1 }}>
          Scheduling Platform
        </h1>
        <p style={{ color:C.muted, margin:"8px 0 0", fontSize:14 }}>
          Progressive Optimization Genetic Algorithm · Dynamic Programming
        </p>
      </div>

      {instance && (
        <>
          {/* Stats row */}
          <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:14 }}>
            <StatCard icon={BookOpen}   label="Courses"    value={instance.num_courses}        sub={`${instance.num_events} teaching events`}  accent={C.gold}/>
            <StatCard icon={Users}      label="Teachers"   value={instance.num_teachers}       sub={`${instance.num_admin_classes} cohorts`}     accent={C.blue}/>
            <StatCard icon={Building2}  label="Classrooms" value={instance.num_classrooms}     sub="lecture + lab rooms"                          accent={C.purple}/>
            <StatCard icon={Layers}     label="Joint Evts" value={instance.joint_events}       sub={`of ${instance.num_events} total`}            accent={C.green}/>
          </div>

          {/* Result summary if available */}
          {result ? (
            <div style={{ background:C.s2, border:`1px solid ${C.border}`, borderRadius:12, padding:22 }}>
              <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:18 }}>
                <div style={{ fontSize:14, fontWeight:600, color:C.text, display:"flex", alignItems:"center", gap:8 }}>
                  <Trophy size={16} style={{color:C.gold}}/> Latest Schedule Result
                </div>
                <Tag color={result.feasible?C.green:C.red}>{result.feasible?"Feasible":"Infeasible"}</Tag>
              </div>
              <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:14 }}>
                <MetricBox label="Final Fitness"    value={result.final_fitness.toFixed(1)}   accent={C.gold}/>
                <MetricBox label="Hard Violations"  value={result.hard_violations}             accent={result.hard_violations===0?C.green:C.red}/>
                <MetricBox label="Rooms Used"       value={result.classrooms_used}             accent={C.blue}/>
                <MetricBox label="Avg Occupancy"    value={result.occupancy_pct+"%"}           accent={C.purple}/>
              </div>
            </div>
          ) : (
            <div style={{
              background:C.s2, border:`1px dashed ${C.border}`, borderRadius:12,
              padding:40, textAlign:"center",
            }}>
              <Cpu size={36} style={{color:C.goldDim,margin:"0 auto 14px"}}/>
              <div style={{fontSize:16,fontWeight:600,color:C.text,marginBottom:6}}>No schedule generated yet</div>
              <div style={{fontSize:13,color:C.muted,marginBottom:20}}>Configure and run the POGA-DP algorithm to generate an optimized timetable.</div>
              <button onClick={onGenerate} style={{
                background:`linear-gradient(135deg,${C.gold},${C.goldDim})`,
                color:"#0a0b0f", border:"none", borderRadius:8, padding:"10px 24px",
                fontWeight:700, fontSize:13, cursor:"pointer", letterSpacing:"0.04em",
              }}>
                Generate Schedule →
              </button>
            </div>
          )}

          {/* Instance detail */}
          <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:14 }}>
            <InfoTable title="Teaching Staff" rows={instance.teachers.map(t=>[t.name,t.dept])} cols={["Name","Dept"]}/>
            <InfoTable title="Classrooms" rows={instance.classrooms.map(r=>[r.name,`${r.capacity} seats`,r.type])} cols={["Room","Capacity","Type"]}/>
          </div>
        </>
      )}
    </div>
  );
}

function MetricBox({ label, value, accent }) {
  return (
    <div style={{ background:C.s3, borderRadius:8, padding:"14px 16px" }}>
      <div style={{ fontSize:11, color:C.muted, textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:6 }}>{label}</div>
      <div style={{ fontSize:22, fontWeight:700, color:accent, fontFamily:"'JetBrains Mono',monospace" }}>{value}</div>
    </div>
  );
}

function InfoTable({ title, rows, cols }) {
  return (
    <div style={{ background:C.s2, border:`1px solid ${C.border}`, borderRadius:12, overflow:"hidden" }}>
      <div style={{ padding:"14px 18px", borderBottom:`1px solid ${C.border}`, fontSize:13, fontWeight:600, color:C.text }}>{title}</div>
      <table style={{ width:"100%", borderCollapse:"collapse" }}>
        <thead>
          <tr>{cols.map(c=>(
            <th key={c} style={{ padding:"8px 16px", textAlign:"left", fontSize:11, color:C.muted, textTransform:"uppercase", letterSpacing:"0.06em", fontWeight:500 }}>{c}</th>
          ))}</tr>
        </thead>
        <tbody>
          {rows.map((row,i)=>(
            <tr key={i} style={{ borderTop:`1px solid ${C.border}33` }}>
              {row.map((cell,j)=>(
                <td key={j} style={{ padding:"9px 16px", fontSize:12.5, color: j===0?C.text:C.muted }}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ══ GENERATE ══ */
function Generate({ config, setConfig, onRun, generating, instance }) {
  const update = (k,v) => setConfig(p => ({...p,[k]:v}));
  const soft = { sc1:"Course Distribution",sc2:"Admin Day Balance",sc3:"Teacher Day Balance",sc4:"Teacher Preference",sc5:"Room Utilisation" };

  return (
    <div style={{maxWidth:720, display:"flex", flexDirection:"column", gap:22}}>
      <div>
        <h2 style={{fontFamily:"'Cormorant Garamond',serif",fontSize:26,fontWeight:700,color:C.text,margin:0}}>Schedule Generation</h2>
        <p style={{color:C.muted,margin:"6px 0 0",fontSize:14}}>Configure POGA-DP hyper-parameters then run the algorithm.</p>
      </div>

      {/* GA Params */}
      <Section title="GA Parameters" icon={Settings2}>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
          {[
            ["Population Size","population_size","number",10,200,1],
            ["Max Generations","max_generations","number",50,2000,10],
            ["Crossover Prob (Pc)","crossover_prob","number",0.1,1.0,0.05],
            ["Mutation Prob (Pm)","mutation_prob","number",0.001,0.2,0.001],
            ["Tournament k","tournament_k","number",2,10,1],
            ["Time Limit (sec)","time_limit_sec","number",30,3600,30],
          ].map(([label,key,type,min,max,step])=>(
            <label key={key} style={{display:"flex",flexDirection:"column",gap:6}}>
              <span style={{fontSize:12,color:C.muted,letterSpacing:"0.04em"}}>{label}</span>
              <input
                type={type} min={min} max={max} step={step}
                value={config[key]}
                onChange={e=>update(key,type==="number"?parseFloat(e.target.value):e.target.value)}
                style={{
                  background:C.s3, border:`1px solid ${C.border}`, borderRadius:8,
                  color:C.text, padding:"9px 12px", fontSize:13,
                  fontFamily:"'JetBrains Mono',monospace",
                }}
              />
            </label>
          ))}
        </div>
      </Section>

      {/* Algorithm info */}
      <Section title="Algorithm Phases" icon={Layers}>
        <div style={{display:"flex",flexDirection:"column",gap:10}}>
          {["Phase 1: GA on joint (combined) courses — ensures cohort alignment","Phase 2: GA on independent courses — maximises teacher preference","Phase 3: DP classroom allocation — minimises seat wastage"].map((p,i)=>(
            <div key={i} style={{display:"flex",gap:12,alignItems:"flex-start"}}>
              <div style={{
                width:22,height:22,borderRadius:"50%",background:`${C.gold}22`,border:`1px solid ${C.goldDim}`,
                color:C.gold,fontSize:11,fontWeight:700,display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0,marginTop:1,
              }}>{i+1}</div>
              <span style={{fontSize:13,color:C.muted,lineHeight:1.6}}>{p}</span>
            </div>
          ))}
        </div>
      </Section>

      {/* Run button */}
      <button onClick={onRun} disabled={generating} style={{
        background: generating ? C.s3 : `linear-gradient(135deg,${C.gold},${C.goldDim})`,
        color: generating ? C.muted : "#0a0b0f",
        border:"none", borderRadius:10, padding:"14px 0",
        fontWeight:700, fontSize:14, cursor: generating?"not-allowed":"pointer",
        display:"flex", alignItems:"center", justifyContent:"center", gap:10,
        letterSpacing:"0.04em", transition:"all .2s",
      }}>
        {generating ? <><Loader2 size={17} style={{animation:"spin 1s linear infinite"}}/> Running POGA-DP...</>
                     : <><Play size={17}/> Start Schedule Generation</>}
      </button>
    </div>
  );
}

function Section({ title, icon:Icon, children }) {
  return (
    <div style={{background:C.s2,border:`1px solid ${C.border}`,borderRadius:12,overflow:"hidden"}}>
      <div style={{padding:"14px 20px",borderBottom:`1px solid ${C.border}`,display:"flex",alignItems:"center",gap:8}}>
        <Icon size={14} style={{color:C.gold}}/><span style={{fontSize:13,fontWeight:600,color:C.text}}>{title}</span>
      </div>
      <div style={{padding:20}}>{children}</div>
    </div>
  );
}

/* ══ JOBS ══ */
function Jobs({ jobs, activeJob, result }) {
  if(!jobs.length) return (
    <div style={{color:C.muted,fontSize:14,padding:40,textAlign:"center"}}>
      <Clock size={32} style={{marginBottom:12,opacity:.4}}/><br/>No jobs started yet. Go to <b>Generate</b> to create a schedule.
    </div>
  );

  return (
    <div style={{display:"flex",flexDirection:"column",gap:14}}>
      <h2 style={{fontFamily:"'Cormorant Garamond',serif",fontSize:26,fontWeight:700,color:C.text,margin:0}}>Generation Jobs</h2>
      {jobs.map(job => (
        <div key={job.job_id} style={{
          background:C.s2, border:`1px solid ${job.job_id===activeJob?C.goldDim:C.border}`,
          borderRadius:12, padding:20,
        }}>
          <div style={{display:"flex",alignItems:"center",gap:12,marginBottom:14}}>
            <span style={{fontFamily:"'JetBrains Mono',monospace",fontSize:12,color:C.gold,background:`${C.gold}12`,padding:"3px 10px",borderRadius:6}}>#{job.job_id}</span>
            <StatusBadge status={job.status}/>
            <span style={{marginLeft:"auto",color:C.muted,fontSize:12}}>{job.instance}</span>
          </div>

          {/* Progress bar */}
          {(job.status==="RUNNING"||job.status==="PENDING") && (
            <div style={{marginBottom:14}}>
              <div style={{height:4,background:C.s3,borderRadius:99,overflow:"hidden"}}>
                <div style={{
                  height:"100%",borderRadius:99,
                  width:`${job.progress||0}%`,
                  background:`linear-gradient(90deg,${C.gold},${C.blue})`,
                  transition:"width .4s ease",
                }}/>
              </div>
              <div style={{fontSize:11,color:C.muted,marginTop:6,display:"flex",justifyContent:"space-between"}}>
                <span style={{animation:"pulse 1.5s ease infinite"}}>● Optimizing…</span>
                <span>{job.progress||0}%</span>
              </div>
            </div>
          )}

          {/* Result summary */}
          {job.status==="COMPLETED" && result && (
            <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10}}>
              <MetricBox label="Fitness"      value={result.final_fitness.toFixed(1)} accent={C.gold}/>
              <MetricBox label="Violations"   value={result.hard_violations}          accent={result.hard_violations===0?C.green:C.red}/>
              <MetricBox label="Rooms"        value={result.classrooms_used}          accent={C.blue}/>
              <MetricBox label="Occupancy"    value={result.occupancy_pct+"%"}        accent={C.purple}/>
            </div>
          )}

          {job.status==="FAILED" && (
            <div style={{color:C.red,fontSize:13}}><AlertCircle size={14} style={{marginRight:6,verticalAlign:"middle"}}/>Job failed</div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ══ TIMETABLE ══ */
const DAYS = ["Mon","Tue","Wed","Thu","Fri"];
const PERIODS = ["P1","P2","P3","P4","P5"];

function Timetable({ timetable, instance, onLoadClass, result, selectedClass }) {
  const courseColors = useRef({});
  let colorIdx = 0;
  const getColor = (code) => {
    if(!code) return null;
    if(!courseColors.current[code]) courseColors.current[code] = COURSE_PALETTE[colorIdx++ % COURSE_PALETTE.length];
    return courseColors.current[code];
  };

  if(!result) return (
    <div style={{color:C.muted,fontSize:14,padding:40,textAlign:"center"}}>
      <Grid3x3 size={32} style={{marginBottom:12,opacity:.4}}/><br/>Generate a schedule first to view the timetable.
    </div>
  );

  return (
    <div style={{display:"flex",flexDirection:"column",gap:22}}>
      <div style={{display:"flex",alignItems:"flex-end",justifyContent:"space-between"}}>
        <div>
          <h2 style={{fontFamily:"'Cormorant Garamond',serif",fontSize:26,fontWeight:700,color:C.text,margin:0}}>Timetable View</h2>
          <p style={{color:C.muted,margin:"6px 0 0",fontSize:14}}>Weekly schedule grid — select an admin class to filter</p>
        </div>
        {timetable && <Tag color={C.blue}>{timetable.events_count} events shown</Tag>}
      </div>

      {/* Class selector */}
      {instance && (
        <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
          {instance.admin_classes.map(cls=>(
            <button key={cls.id} onClick={()=>onLoadClass(cls.name)} style={{
              padding:"6px 14px", borderRadius:99, border:`1px solid ${selectedClass===cls.name?C.gold:C.border}`,
              background: selectedClass===cls.name?`${C.gold}18`:"transparent",
              color: selectedClass===cls.name?C.gold:C.muted,
              fontSize:12, fontWeight:600, cursor:"pointer", transition:"all .15s",
            }}>{cls.name}</button>
          ))}
        </div>
      )}

      {/* Grid */}
      {timetable && (
        <div style={{background:C.s2,border:`1px solid ${C.border}`,borderRadius:12,overflow:"hidden"}}>
          <table style={{width:"100%",borderCollapse:"collapse"}}>
            <thead>
              <tr style={{background:C.s3}}>
                <th style={{padding:"12px 16px",textAlign:"left",fontSize:11,color:C.muted,letterSpacing:"0.08em",textTransform:"uppercase",width:60}}>Period</th>
                {DAYS.map(d=>(
                  <th key={d} style={{padding:"12px 16px",textAlign:"center",fontSize:11,color:C.muted,letterSpacing:"0.08em",textTransform:"uppercase",borderLeft:`1px solid ${C.border}`}}>{d}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {timetable.grid.map((row,pi)=>(
                <tr key={pi} style={{borderTop:`1px solid ${C.border}`}}>
                  <td style={{padding:"8px 16px",fontSize:11,color:C.muted,fontFamily:"'JetBrains Mono',monospace",fontWeight:600,background:C.s3}}>
                    {row.period}
                  </td>
                  {DAYS.map(d=>{
                    const cell = row.days[d];
                    if(!cell?.course) return (
                      <td key={d} style={{borderLeft:`1px solid ${C.border}`,minHeight:70}}/>
                    );
                    const color = getColor(cell.course);
                    return (
                      <td key={d} style={{borderLeft:`1px solid ${C.border}`,padding:8,verticalAlign:"top"}}>
                        <div style={{
                          background:`${color}18`,border:`1px solid ${color}44`,
                          borderRadius:8,padding:"8px 10px",
                          borderLeft:`3px solid ${color}`,
                        }}>
                          <div style={{fontSize:12,fontWeight:700,color,marginBottom:3,fontFamily:"'JetBrains Mono',monospace"}}>{cell.course}</div>
                          <div style={{fontSize:11,color:C.muted,lineHeight:1.5}}>
                            {cell.teacher.split(" ").slice(0,2).join(" ")}<br/>
                            <span style={{color:C.text.replace("ee","bb"),fontSize:10}}>{cell.room}</span>
                          </div>
                          {cell.joint && <div style={{marginTop:4}}><Tag color={C.purple}>joint</Tag></div>}
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Legend */}
      {Object.keys(courseColors.current).length > 0 && (
        <div style={{display:"flex",gap:10,flexWrap:"wrap"}}>
          {Object.entries(courseColors.current).map(([code,color])=>(
            <div key={code} style={{display:"flex",alignItems:"center",gap:6,fontSize:12,color:C.muted}}>
              <div style={{width:10,height:10,borderRadius:3,background:color}}/>{code}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ══ ANALYTICS ══ */
function Analytics({ result, hist }) {
  if(!result) return (
    <div style={{color:C.muted,fontSize:14,padding:40,textAlign:"center"}}>
      <BarChart2 size={32} style={{marginBottom:12,opacity:.4}}/><br/>Run a schedule generation first.
    </div>
  );

  const chartData = hist.best.map((b,i)=>({ gen:i, best:Math.round(b), avg:Math.round(hist.avg[i]) }));
  const bd = result.fitness_breakdown;
  const soft = bd.soft_detail;

  const softMax = Math.max(...Object.entries(soft).filter(([k])=>k!=="total").map(([,v])=>v));

  return (
    <div style={{display:"flex",flexDirection:"column",gap:22}}>
      <h2 style={{fontFamily:"'Cormorant Garamond',serif",fontSize:26,fontWeight:700,color:C.text,margin:0}}>Analytics</h2>

      {/* Fitness evolution */}
      <Section title="Fitness Evolution" icon={BarChart2}>
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={chartData} margin={{top:5,right:10,left:10,bottom:5}}>
            <defs>
              <linearGradient id="goldGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={C.gold} stopOpacity={0.3}/>
                <stop offset="95%" stopColor={C.gold} stopOpacity={0}/>
              </linearGradient>
              <linearGradient id="blueGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={C.blue} stopOpacity={0.15}/>
                <stop offset="95%" stopColor={C.blue} stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={C.border}/>
            <XAxis dataKey="gen" tick={{fill:C.muted,fontSize:11}} label={{value:"Generation",position:"insideBottom",offset:-2,fill:C.muted,fontSize:11}}/>
            <YAxis tick={{fill:C.muted,fontSize:11}} tickFormatter={v=>v>=1e6?`${(v/1e6).toFixed(1)}M`:v}/>
            <Tooltip contentStyle={{background:C.s3,border:`1px solid ${C.border}`,borderRadius:8,fontSize:12}} labelStyle={{color:C.text}} formatter={v=>[v.toLocaleString()]}/>
            <Legend iconType="circle" iconSize={8} wrapperStyle={{fontSize:12,paddingTop:10}}/>
            <Area type="monotone" dataKey="avg" stroke={C.blue} strokeWidth={1.5} fill="url(#blueGrad)" dot={false} name="Avg Fitness"/>
            <Area type="monotone" dataKey="best" stroke={C.gold} strokeWidth={2} fill="url(#goldGrad)" dot={false} name="Best Fitness"/>
          </AreaChart>
        </ResponsiveContainer>
      </Section>

      {/* Soft penalties breakdown */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14}}>
        <Section title="Soft Constraint Penalties" icon={ArrowUpDown}>
          <div style={{display:"flex",flexDirection:"column",gap:12}}>
            {Object.entries(soft).filter(([k])=>k!=="total").map(([key,val])=>{
              const labels = {sc1:"Course Distribution",sc2:"Admin Day Balance",sc3:"Teacher Day Balance",sc4:"Teacher Preference",sc5:"Room Utilisation"};
              const pct = softMax>0 ? (val/softMax*100) : 0;
              return (
                <div key={key}>
                  <div style={{display:"flex",justifyContent:"space-between",marginBottom:5,fontSize:12}}>
                    <span style={{color:C.muted}}>{labels[key]}</span>
                    <span style={{color:C.text,fontFamily:"'JetBrains Mono',monospace",fontWeight:600}}>{val.toFixed(2)}</span>
                  </div>
                  <div style={{height:5,background:C.s3,borderRadius:99,overflow:"hidden"}}>
                    <div style={{height:"100%",width:`${pct}%`,background:C.gold,borderRadius:99,transition:"width .6s"}}/>
                  </div>
                </div>
              );
            })}
          </div>
        </Section>

        <Section title="Hard Constraints" icon={CheckCircle}>
          <div style={{display:"flex",flexDirection:"column",gap:10}}>
            {Object.entries(bd.hard_detail).map(([k,v])=>(
              <div key={k} style={{display:"flex",alignItems:"center",justifyContent:"space-between",padding:"8px 12px",background:C.s3,borderRadius:8}}>
                <span style={{fontSize:12,color:C.muted}}>{k.replace(/_/g," ")}</span>
                <div style={{display:"flex",alignItems:"center",gap:6}}>
                  {v===0 ? <CheckCircle size={13} style={{color:C.green}}/> : <AlertCircle size={13} style={{color:C.red}}/>}
                  <span style={{fontSize:12,fontFamily:"'JetBrains Mono',monospace",color:v===0?C.green:C.red,fontWeight:700}}>{v}</span>
                </div>
              </div>
            ))}
          </div>
        </Section>
      </div>

      {/* Summary */}
      <div style={{background:C.s2,border:`1px solid ${C.gold}33`,borderRadius:12,padding:20,display:"flex",gap:20}}>
        <div style={{flex:1}}>
          <div style={{fontSize:11,color:C.muted,textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:6}}>Final Fitness</div>
          <div style={{fontSize:36,fontWeight:700,fontFamily:"'Cormorant Garamond',serif",color:C.gold}}>{result.final_fitness.toFixed(1)}</div>
          <div style={{fontSize:12,color:C.muted}}>Pure soft penalty (0 hard violations)</div>
        </div>
        <div style={{width:1,background:C.border}}/>
        <div style={{flex:1}}>
          <div style={{fontSize:11,color:C.muted,textTransform:"uppercase",letterSpacing:"0.06em",marginBottom:6}}>Soft Breakdown</div>
          {Object.entries(soft).filter(([k])=>k!=="total").map(([k,v])=>(
            <div key={k} style={{display:"flex",justifyContent:"space-between",fontSize:12,color:C.muted,marginBottom:3}}>
              <span>{k.toUpperCase()}</span><span style={{color:C.text}}>{v.toFixed(2)}</span>
            </div>
          ))}
          <div style={{display:"flex",justifyContent:"space-between",fontSize:12,fontWeight:700,color:C.gold,borderTop:`1px solid ${C.border}`,paddingTop:4,marginTop:4}}>
            <span>TOTAL</span><span>{soft.total.toFixed(2)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ══ EXPORT ══ */
function Export({ activeJob, result, demoMode }) {
  const [copied, setCopied] = useState(false);
  if(!result) return (
    <div style={{color:C.muted,fontSize:14,padding:40,textAlign:"center"}}>
      <FileDown size={32} style={{marginBottom:12,opacity:.4}}/><br/>Generate a schedule first.
    </div>
  );

  const csvUrl = demoMode ? null : `${API}/schedules/${activeJob}/export/csv`;
  const jsonUrl = demoMode ? null : `${API}/schedules/${activeJob}/export/json`;

  const copyJson = () => {
    navigator.clipboard.writeText(JSON.stringify(MOCK_RESULT, null, 2));
    setCopied(true); setTimeout(()=>setCopied(false),2000);
  };

  return (
    <div style={{display:"flex",flexDirection:"column",gap:22,maxWidth:620}}>
      <h2 style={{fontFamily:"'Cormorant Garamond',serif",fontSize:26,fontWeight:700,color:C.text,margin:0}}>Export Schedule</h2>

      {[
        { title:"CSV Export", desc:"Download all scheduled events as a spreadsheet-ready CSV file.", icon:FileDown, color:C.green, url:csvUrl, label:"Download CSV", ext:"csv" },
        { title:"JSON Export", desc:"Full schedule data including fitness breakdown and room assignments.", icon:Database, color:C.blue, url:jsonUrl, label:"Download JSON", ext:"json" },
      ].map(({ title, desc, icon:Icon, color, url, label, ext })=>(
        <div key={ext} style={{background:C.s2,border:`1px solid ${C.border}`,borderRadius:12,padding:22,display:"flex",alignItems:"center",gap:18}}>
          <div style={{width:48,height:48,borderRadius:10,background:`${color}18`,display:"flex",alignItems:"center",justifyContent:"center",flexShrink:0}}>
            <Icon size={22} style={{color}}/>
          </div>
          <div style={{flex:1}}>
            <div style={{fontSize:14,fontWeight:600,color:C.text,marginBottom:4}}>{title}</div>
            <div style={{fontSize:12,color:C.muted}}>{desc}</div>
          </div>
          {url ? (
            <a href={url} download style={{
              background:`${color}22`,border:`1px solid ${color}44`,color,
              borderRadius:8,padding:"8px 16px",fontSize:12,fontWeight:600,
              textDecoration:"none",display:"flex",alignItems:"center",gap:6,
            }}><Download size={13}/>{label}</a>
          ) : (
            <button onClick={ext==="json"?copyJson:undefined} style={{
              background:`${color}22`,border:`1px solid ${color}44`,color,
              borderRadius:8,padding:"8px 16px",fontSize:12,fontWeight:600,cursor:"pointer",
              display:"flex",alignItems:"center",gap:6,
            }}>
              <Copy size={13}/>{ext==="json" && copied ? "Copied!" : label}
            </button>
          )}
        </div>
      ))}

      {/* iCal note */}
      <div style={{background:`${C.purple}12`,border:`1px solid ${C.purple}33`,borderRadius:10,padding:16}}>
        <div style={{fontSize:13,fontWeight:600,color:C.purple,marginBottom:4,display:"flex",alignItems:"center",gap:8}}>
          <CalendarDays size={14}/>iCal / Calendar Integration
        </div>
        <div style={{fontSize:12,color:C.muted}}>
          iCal export (UC9) is supported via <code style={{fontFamily:"monospace",color:C.purple}}>GET /schedules/{"{job_id}"}/export/ical</code>. Connect directly to Google Calendar, Outlook, or Apple Calendar.
        </div>
      </div>

      {/* API access */}
      <div style={{background:C.s2,border:`1px solid ${C.border}`,borderRadius:12,padding:22}}>
        <div style={{fontSize:13,fontWeight:600,color:C.text,marginBottom:14,display:"flex",alignItems:"center",gap:8}}>
          <Cpu size={14} style={{color:C.gold}}/> API Access
        </div>
        {[
          ["GET",`/schedules/${activeJob||"{job_id}"}/export/csv`,C.green],
          ["GET",`/schedules/${activeJob||"{job_id}"}/export/json`,C.blue],
          ["GET",`/schedules/${activeJob||"{job_id}"}/timetable`,C.gold],
          ["GET",`/schedules/compare?job_ids=id1,id2`,C.purple],
        ].map(([method,path,color])=>(
          <div key={path} style={{display:"flex",alignItems:"center",gap:10,marginBottom:8}}>
            <Tag color={color}>{method}</Tag>
            <code style={{fontSize:11,color:C.muted,fontFamily:"'JetBrains Mono',monospace"}}>{API}{path}</code>
          </div>
        ))}
      </div>
    </div>
  );
}
