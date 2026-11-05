/* SPDX-License-Identifier: BSD-2-Clause */
#define NATIVE_FOLIO_BATCH_TEST 1
#include "linux_folio_batch.c"
static unsigned int cases;
static void pass(const char *name) { printf("PASS %u %s\n",++cases,name);fflush(stdout); }
static void populate(struct page *pages,struct linux_folio *folios,unsigned int count)
{ for(unsigned int i=0;i<count;i++){pages[i]=(struct page){.refs=1,.wires=1};folios[i].netbsd_page=pages+i;} }
static void positive(void)
{ struct page pages[31];struct linux_folio folios[31];struct folio_batch batch;populate(pages,folios,31);
  folio_batch_init(&batch);assert(folio_batch_count(&batch)==0&&folio_batch_space(&batch)==31&&folio_batch_next(&batch)==NULL);
  folio_batch_release(&batch);pass("empty-batch-no-reference-consumption");
  for(unsigned int i=0;i<31;i++)assert(folio_batch_add(&batch,folios+i)==30-i);
  assert(folio_batch_count(&batch)==31&&folio_batch_space(&batch)==0);
  for(unsigned int i=0;i<31;i++)assert(pages[i].refs==1&&pages[i].puts==0);
  pass("capacity-return-value-transfers-existing-references");
  for(unsigned int i=0;i<31;i++)assert(folio_batch_next(&batch)==folios+i);
  assert(folio_batch_next(&batch)==NULL);pass("ordered-cursor-does-not-consume-references");
  check_move_unevictable_folios(&batch);
  for(unsigned int i=0;i<31;i++)assert(pages[i].validates==1&&pages[i].refs==1&&pages[i].wires==1&&!pages[i].active);
  pass("validates-actual-wire-before-native-last-unwire");
  __folio_batch_release(&batch);assert(batch.nr==0&&batch.i==0);
  for(unsigned int i=0;i<31;i++)assert(pages[i].refs==0&&pages[i].wires==0&&pages[i].puts==1&&pages[i].active&&batch.folios[i]==NULL);
  folio_batch_release(&batch);
  for(unsigned int i=0;i<31;i++)assert(pages[i].puts==1);
  pass("release-each-owner-once-reset-idempotent-empty-release");
  populate(pages,folios,1);pages[0].refs=2;folio_batch_add(&batch,folios);folio_batch_release(&batch);
  assert(pages[0].refs==1&&pages[0].wires==1&&!pages[0].active);pass("external-owner-keeps-native-page-wired");
  populate(pages,folios,1);folio_batch_add(&batch,folios);__folio_batch_release(&batch);
  assert(pages[0].validates==1&&pages[0].puts==1);pass("direct-release-validates-before-consumption");
  folio_batch_reinit(&batch);assert(batch.nr==0&&batch.i==0&&folio_batch_space(&batch)==31);
  pass("reinitialized-empty-batch-reusable"); }
static void fatal_case(const char *name)
{ struct page pages[31];struct linux_folio folios[31];struct folio_batch batch;
  populate(pages,folios,31);folio_batch_init(&batch);
  if(!strcmp(name,"full")){for(unsigned int i=0;i<31;i++)folio_batch_add(&batch,folios+i);folio_batch_add(&batch,folios);}
  else if(!strcmp(name,"null"))folio_batch_add(&batch,NULL);
  else if(!strcmp(name,"bad-count")){batch.nr=32;(void)folio_batch_count(&batch);}
  else if(!strcmp(name,"bad-cursor")){batch.i=1;(void)folio_batch_next(&batch);}
  else if(!strcmp(name,"missing-wire")){pages[0].wires=0;folio_batch_add(&batch,folios);__folio_batch_release(&batch);}
  else if(!strcmp(name,"dead-owner")){pages[0].refs=0;folio_batch_add(&batch,folios);check_move_unevictable_folios(&batch);}
  else panic("unknown fatal case");
  panic("fatal case unexpectedly returned"); }
int main(int argc,char **argv)
{ alarm(20);if(argc==2){fatal_case(argv[1]);return 99;}assert(argc==1);positive();assert(cases==8);
  puts("NATIVE_FOLIO_BATCH_MODEL_PASS cases=8 native_kernel_acceptance=OPEN");return 0; }
