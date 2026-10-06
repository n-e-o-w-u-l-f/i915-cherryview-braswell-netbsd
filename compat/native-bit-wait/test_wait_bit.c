/* SPDX-License-Identifier: BSD-2-Clause */
/* Complete actual production source, explicit model declarations above it. */
#include "test_model.h"
#ifndef HP_BIT_SOURCE
#define HP_BIT_SOURCE "linux_wait_bit.c"
#endif
#include HP_BIT_SOURCE
static volatile unsigned long word[2];
static unsigned cases;
static void reset(unsigned signal)
{
 word[0]=1;word[1]=0;model_word=word;model_bit=0;model_virtual=true;
 model_signal=signal;model_calls=0;model_mode=99;model_ticks=0;
 model_acquires=0;model_releases=0;model_full=0;model_error=0;
 model_spurious=0;model_clear_at=1;model_clear_elapsed=3;
}
static void fast_clear(void)
{
 reset(2);word[0]=0;
 assert(wait_on_bit(word,0,TASK_KILLABLE)==0);
 assert(wait_on_bit_timeout(word,0,TASK_KILLABLE,0)==0);
 assert(model_calls==0 && model_acquires==2);cases++;
}
static void success_zero(void)
{
 reset(0);assert(wait_on_bit_timeout(word,0,TASK_UNINTERRUPTIBLE,10)==0);
 assert(model_calls==1 && model_ticks==3 && model_acquires>=1);cases++;
 reset(0);assert(wait_on_bit(word,0,TASK_UNINTERRUPTIBLE)==0);
 assert(model_calls==1 && model_mode==0 && model_acquires>=1);cases++;
}
static void fatal_policy(void)
{
 for(unsigned s=0;s<5;s++){
  reset(s);
  int ret=wait_on_bit_timeout(word,0,TASK_KILLABLE,10);
  assert(model_mode==2);
  assert(ret==(s>=2 ? -EINTR : 0));
  assert(test_bit(0,word)==(s>=2));cases++;
  reset(s);
  ret=wait_on_bit_timeout(word,0,TASK_INTERRUPTIBLE|TASK_WAKEKILL,10);
  assert(model_mode==1);assert(ret==(s ? -EINTR : 0));cases++;
  reset(s);
  ret=wait_on_bit_timeout(word,0,TASK_IDLE,10);
  assert(model_mode==0 && ret==0);cases++;
 }
 reset(2);assert(wait_on_bit(word,0,TASK_KILLABLE)==-EINTR);
 assert(model_mode==2);cases++;
 for(unsigned mode=0;mode<2;mode++){
  reset(0);model_error=mode ? ERESTART : EINTR;
  assert(wait_on_bit_timeout(word,0,TASK_INTERRUPTIBLE,10)==-EINTR);cases++;
 }
}
static void wide_timeout(void)
{
 unsigned long slice=INT_MAX/2;
 reset(0);model_clear_at=0;model_ticks=UINT_MAX-4;
 unsigned start=model_ticks;unsigned long budget=slice*3+7;
 assert(wait_on_bit_timeout(word,0,TASK_UNINTERRUPTIBLE,budget)==-EAGAIN);
 assert(model_calls==4 && model_ticks==(unsigned)(start+budget));cases++;
 reset(0);model_clear_at=3;model_clear_elapsed=13;model_ticks=UINT_MAX-4;
 start=model_ticks;
 assert(wait_on_bit_timeout(word,0,TASK_UNINTERRUPTIBLE,budget)==0);
 assert(model_calls==3 && model_ticks==(unsigned)(start+slice*2+13));cases++;
 reset(0);model_clear_at=0;
 assert(wait_on_bit_timeout(word,0,TASK_UNINTERRUPTIBLE,0)==-EAGAIN);
 assert(model_calls==0);cases++;
 reset(0);model_spurious=100;model_clear_at=101;
 assert(wait_on_bit_timeout(word,0,TASK_UNINTERRUPTIBLE,10)==0);
 assert(model_calls==101 && model_ticks==3);cases++;
}
static void publication(void)
{
 reset(0);clear_and_wake_up_bit(0,word);
 assert(!test_bit(0,word) && model_releases==1 && model_full==1);cases++;
 reset(0);word[1]=1UL<<9;model_word=word;model_bit=sizeof(long)*CHAR_BIT+9;
 assert(wait_on_bit_timeout(word,model_bit,TASK_UNINTERRUPTIBLE,10)==0);
 assert(!test_bit(model_bit,word));cases++;
}
struct thread_case { unsigned payload,observed;int result; };
static void *reader(void *arg)
{
 struct thread_case *c=arg;model_virtual=false;model_signal=0;
 c->result=wait_on_bit(word,0,TASK_UNINTERRUPTIBLE);c->observed=c->payload;
 assert(model_acquires>0);return NULL;
}
static void real_pthread_wake(void)
{
 model_virtual=false;
 for(unsigned i=1;i<=64;i++){
  word[0]=1;struct thread_case c={0,0,-999};pthread_t t;
  assert(pthread_create(&t,NULL,reader,&c)==0);
  kcondvar_t *cv=&waitbittab[wait_bit_hash(word,0)].ent.cv;
  unsigned start=getticks();
  while(!atomic_load_explicit(&cv->waiters,memory_order_acquire)){
   assert((unsigned)(getticks()-start)<3000);sched_yield();
  }
  c.payload=i;clear_and_wake_up_bit(0,word);
  assert(pthread_join(t,NULL)==0 && c.result==0 && c.observed==i);
  cases++;
 }
}
int main(int argc,char **argv)
{
 assert(linux_wait_bit_init()==0);
 if(argc==2){
  if(!strcmp(argv[1],"success"))success_zero();
  else if(!strcmp(argv[1],"wide"))wide_timeout();
  else if(!strcmp(argv[1],"fatal"))fatal_policy();
  else if(!strcmp(argv[1],"ordering")){fast_clear();publication();}
  else abort();
 }else {fast_clear();success_zero();fatal_policy();wide_timeout();publication();real_pthread_wake();}
 linux_wait_bit_fini();printf("ACTUAL_NATIVE_BIT_WAIT_MODEL_PASS cases=%u\n",cases);return 0;
}
