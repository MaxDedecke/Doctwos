from java.parse import parse_java_file
from java.resolution import resolve_global_edges

def inspect(name, files):
    results=[parse_java_file(code, f'mod/src/main/java/demo/{cls}.java') for cls,code in files.items()]
    resolve_global_edges(results)
    print('\nCASE',name,flush=True)
    for r in results:
        print('FILE',r.path,'DIAGNOSTICS',[(d.code,d.line,d.message[:100]) for d in r.diagnostics],flush=True)
        print('ENTITIES',[(e.type,e.name,e.qualified_name,e.start_line,e.meta) for e in r.entities if e.type in {'method','lambda','anonymous_class','local_variable','method_reference','field'}],flush=True)
        print('EDGES',[(e.type,e.src_name,e.dst_name,e.resolution,(e.meta or {}).get('target_qualified_name'),(e.meta or {}).get('resolution_reason'),e.src_start_line) for e in r.edges if e.type in {'CALLS','READS','WRITES','INSTANTIATES'}],flush=True)
inspect('lambda',{'A':'''package demo;
class A {
 void outer() { Runnable r = () -> helper(); }
 void helper() {}
}'''})
inspect('anonymous',{'A':'''package demo;
class A {
 interface Job { void run(); }
 void outer() { Job j = new Job() { public void run() { helper(); } }; }
 void helper() {}
}'''})
inspect('shadow',{'A':'''package demo;
class A {
 void run() {
   Target first = new Target();
   first.work();
   { Other first = new Other(); first.work(); }
 }
}
class Target { void work() {} }
class Other { void work() {} }'''})
inspect('method_ref',{'A':'''package demo;
class A {
 void outer() { Runnable r = this::helper; }
 void helper() {}
}'''})
inspect('field',{'A':'''package demo;
class A {
 int count;
 void run() { count = 2; count += 3; int n = count; }
}'''})
inspect('chain',{'A':'''package demo;
class A { B getB() { return new B(); } void run() { getB().work(); } }
class B { void work() {} }'''})
inspect('anonymous_this',{'A':'''package demo;
class A {
 void helper() {}
 void outer() {
  Runnable r = new Runnable() {
   public void run() { this.helper(); }
   void helper() {}
  };
 }
}'''})
inspect('cross_file_field',{
 'A':'package demo; class A { B b; void run() { b.value=1; int x=b.value; } }',
 'B':'package demo; class B { int value; }',
})
inspect('exception_flow',{'A':'''package demo;
class A {
 void run() throws java.io.IOException {
  try { work(); }
  catch (java.io.IOException ex) { recover(); }
  finally { close(); }
 }
 void work() throws java.io.IOException {}
 void recover() {}
 void close() {}
}'''})
inspect('annotation_value',{'A':'''package demo;
@interface Flag { String value(); }
class A { @Flag("critical") void run() {} }'''})
