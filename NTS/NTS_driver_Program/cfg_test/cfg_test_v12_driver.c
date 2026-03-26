#include <stdio.h>
#include <stdlib.h>
#include <assert.h>

void f_1(int);
void g_1(int);
void h_1(int);
void i_1(int);


void f_1(int a) {
  if (a > 13) {
    printf("\ngreater than 13\n");
  } else {
    printf("\nnot greater than 13\n");
  }
}

void g_1(int a) {
  h_1(a);

  if (a == 7) {
    printf("\n7\n");
  } else {
    printf("\nnot 7\n");
  }

  i_1(a);
}

void h_1(int a) {
  if (a == -4) {
    printf("\n-4\n");
  } else {
    printf("\nnot -4\n");
  }
}

void i_1(int a) {
  if (a == 100) {
    printf("\n100\n");
  } else {
    printf("\nnot 100\n");
  }
}


//--------------------------------------------------------------------------------------------------------------------
void f_2(int);
void g_2(int);
void h_2(int);
void i_2(int);


void f_2(int a) {
  if (a > 13) {
    printf("\ngreater than 13\n");
  } else {
    printf("\nnot greater than 13\n");
  }
}

void g_2(int a) {
  h_2(a);

  if (a == 7) {
    printf("\n7\n");
  } else {
    printf("\nnot 7\n");
  }

  i_2(a);
}

void h_2(int a) {
  if (a == -4) {
    printf("\nnot -4\n");
  } else {
    printf("\nnot -4\n");
  }
}

void i_2(int a) {
  if (a == 100) {
    printf("\n100\n");
  } else {
    printf("\nnot 100\n");
  }
}



int main_1(int a) {
  if (a == 19) {
    printf("\n19\n");
  } else {
    printf("\nnot 19\n");
  }
 
  if (a> 5){
	printf("\nThe value of is greater than 5");
	printf("\nThe value of a is %d", a);
  	f_1(a);
	}
   if (a< 5){
	printf("\nThe value of is less than 5");
	printf("\nThe value of a is %d", a);
  	g_1(a);
	}
    if (a==5){
        printf("\nThe value of is equal to 5");
	printf("\nThe value of a is %d", a);
	f_1(a);
  	g_1(a);
	}
  f_1(a);
  g_1(a);

  if (a != 1) {
    printf("\nnot 1\n");
  } else {
    printf("\n1\n");
  }

  return 0;
}

int main_2(int a) {

  if (a == 19) {
    printf("\n19\n");
  } else {
    printf("\nnot 19\n");
  }
 
  if (a> 5){
	printf("\nThe value of is greater than 5");
	printf("\nThe value of a is %d", a);
  	f_2(a);
	}
   if (a< 5){
	printf("\nThe value of is less than 5");
	printf("\nThe value of a is %d", a);
  	g_2(a);
	}
    if (a==5){
        printf("\nThe value of is equal to 5");
	printf("\nThe value of a is %d", a);
	f_2(a);
  	g_2(a);
	}
  f_2(a);
  g_2(a);

  if (a != 1) {
    printf("\nnot 1\n");
  } else {
    printf("\n1\n");
  }

  return 0;
}

int main(void) {
  int a;

    // Safe range for square without overflow: [-46340, 46340]
    __CPROVER_assume(a >= -100 && a <= 100);

  main_1(a);
  main_2(a);

  return 0;
}